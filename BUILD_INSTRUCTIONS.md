# Building and Testing Subiquity Changes

## Quick Build Process

### 1. Build the Snap

```bash
snapcraft pack --output subiquity_test.snap
```

This will create a snap file named `subiquity_test.snap` in the current directory.

### 2. Get an Ubuntu ISO

Download a recent Ubuntu Server ISO (daily build recommended):
- Daily builds: https://cdimage.ubuntu.com/ubuntu-server/daily/current/
- Or use a specific release ISO

### 3. Inject the Snap into the ISO

Use the inject script:

```bash
./scripts/inject-subiquity-snap.sh <old_iso> <subiquity_snap> <new_iso>
```

Example:
```bash
./scripts/inject-subiquity-snap.sh \
    ubuntu-24.04-server-amd64.iso \
    subiquity_test.snap \
    ubuntu-24.04-server-amd64-custom.iso
```

### 4. Test the ISO

Boot from the new ISO in a VM or on hardware and test your changes.

## Alternative: Quick Test Script

There's also a quick test script that might help:

```bash
./scripts/quick-test-this-branch.sh
```

## Notes

- The translation files (`.po` files) have been updated for English (`po/en_US.po`)
- If you see old strings, make sure you've rebuilt the snap after making changes
- The snap includes all Python code, so code changes require rebuilding the snap
- Translation changes also require rebuilding the snap

## Troubleshooting

If you're still seeing old strings ("token" instead of "installation key"):

1. **Verify your code changes are saved** - Check that `subiquity/ui/views/homenode_token.py` has the new strings
2. **Clean build** - Try removing any cached build artifacts:
   ```bash
   snapcraft clean
   snapcraft pack --output subiquity_test.snap
   ```
3. **Check the snap contents** - You can verify the snap contains your changes:
   ```bash
   unsquashfs -d /tmp/snap subiquity_test.snap
   grep -r "Installation Key" /tmp/snap/subiquity/
   ```
4. **Verify ISO injection** - Make sure the injection completed successfully

## Development Workflow

For faster iteration during development:

1. Use `make dryrun` to test changes without building a snap
2. Only build the snap when you need to test in a real ISO
3. Use the inject script to quickly update an ISO with new snap builds

