# subiquity & console-conf
> Ubuntu Server Installer & Snappy first boot experience

The repository contains the source for the new server installer (the
"subiquity" part, aka "ubiquity for servers") and for the snappy first
boot experience (the "console-conf" part).

We track bugs in Launchpad at
https://bugs.launchpad.net/subiquity. Snappy first boot issues can
also be discussed in the forum at https://forum.snapcraft.io.

Our localization platform is Launchpad, translations are managed at
https://translations.launchpad.net/ubuntu/+source/subiquity/

To update translation template in launchpad:
 * update po/POTFILES.in with any new files that contain translations
 * execute clean target, i.e. $ debuild -S
 * dput subiquity into Ubuntu

To export and update translations in subiquity:
 * Wait for new subiquity to publish
 * Request fresh translation export from Launchpad at
https://translations.launchpad.net/ubuntu/focal/+source/subiquity/+export
 * wait for export to generate
 * download, unpack, rename .po files into po directory, and commit changes

# Acquire subiquity from source

`git clone https://github.com/canonical/subiquity`

`cd subiquity && make install_deps`

# Testing out the installer Text-UI (TUI)
Subiquity's text UI is available for testing without actually installing
anything to a system or a VM.  Subiquity developers make use of this for rapid
development.  After checking out subiquity you can start it:

`make dryrun`

All of the features are present in dry-run mode.  The installer will emit its
backend configuration files to /tmp/subiquity-config-\* but it won't attempt to
run any installer commands (which would fail without root privileges).  Further,
subiquity can load other machine profiles in case you want to test out the
installer without having access to the machine.  A few sample machine
profiles are available in the repository at ./examples/machines and
can be loaded via the MACHINE make variable:

`make dryrun MACHINE=examples/machines/simple.json`

# Generating machine profiles
Machine profiles are generated from the probert tool.  To collect a machine profile:

`PYTHONPATH=probert ./probert/bin/probert --all > mymachine.json`

# Testing changes in KVM

To try out your changes for real, it is necessary to install them into
an ISO. Rather than building one from scratch, it's much easier to
install your version of subiquity into the daily image. Here's how to
do this:

## Commit your changes locally

If you are only making a change in Subiquity itself, running `git add <modified-file...>`
and then `git commit` should be enough.

Otherwise, if you made any modification to curtin or probert, you need to ensure that:

* The modification is committed inside the relevant repository (i.e., `git add` + `git commit`).
* The relevant `source` property in snapcraft.yaml points to the local
  repository instead of the upstream repository.
* The relevant `source-commit` property in snapcraft.yaml is updated to reflect
  your new revision (one must use the full SHA-1 here).
* The above modifications to snapcraft.yaml are committed.

Example:
```
parts:
  curtin:
    plugin: nil

    # Comment out the original source property, pointing to the upstream repository
    #source: https://git.launchpad.net/curtin
    # Instead, specify the name of the directory where curtin is checked out
    source: curtin
    source-type: git
    # Update the below so it points to the commit ID within the curtin repository
    source-commit: 7c18bf6a24297ed465a341a1f53875b61c878d6b
```

## Build and inject your changes into an ISO

1. Build your changes into a snap:

   ```
   $ snapcraft pack --output subiquity_test.snap
   ```

2. Grab the current version of the installer:

   ```
   $ urlbase=http://cdimage.ubuntu.com/ubuntu-server/daily-live/current
   $ isoname=$(distro-info -d)-live-server-$(dpkg --print-architecture).iso
   $ zsync ${urlbase}/${isoname}.zsync
   ```

3. Run the provided script to make a copy of the downloaded installer
   that has your version of subiquity:

   ```
   $ sudo ./scripts/inject-subiquity-snap.sh ${isoname} subiquity_test.snap custom.iso
   ```

4. Boot the new iso in KVM:

   ```
   $ qemu-img create -f raw target.img 10G
   $ kvm -m 1024 -boot d -cdrom custom.iso -hda target.img -serial stdio
   ```

5. Finally, boot the installed image:

   ```
   $ kvm -m 1024 -hda target.img -serial stdio
   ```

The first three steps are bundled into the script ./scripts/test-this-branch.sh.

# Contributing

Please see our [contributing guidelines](CONTRIBUTING.md).

# Documentation

Subiquity's documentation is hosted at
[https://canonical-subiquity.readthedocs-hosted.com/en/latest/](https://canonical-subiquity.readthedocs-hosted.com/en/latest/).

The documentation source can be found in the [doc/](doc/) folder, which
contains instructions for building a local preview.
