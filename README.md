# subiquity
> Ubuntu Server Installer

# Acquire subiquity from source

`git clone https://github.com/CanonicalLtd/subiquity`

`cd subiquity && make install_deps`

# Testing out the Text-UI (TUI)
SUbiquity's text UI is is available for testing without actually installing
anything to a system or a VM.  Subiquity developers make use of this for rapid
development.  After checking out subiquity you can start it:

`make dryrun`

All of the features are present in dry-run mode.  The installer will emit its
backend configuration files to /tmp/subiquity-config-\* but it won't attempt to
run any installer commands (which would fail without root privileges).  Further,
subiquity can load other machine profiles in case you want to test out the
installer without having access to the machine.  A few sample machine
profiles are available in the repository at ./examples/ and
can be loaded via the MACHINE make variable:

`make dryrun MACHINE=examples/desktop.json`

# Generating machine profiles
Machine profiles are generated from the probert tool.  To collect a machine profile:

`PYTHONPATH=probert ./probert/bin/probert --all > mymachine.json`

# Testing changes in KVM

To try out your changes for real, it is necessary to install them into
an ISO. Rather than building one from scratch, it's much easier to
install your version of subiquity into the daily image. Here's how to
do this:

1. Build your change into a snap:

   ```
   $ snapcraft snap --output subiquity_test.snap
   ```

2. Grab the current version of the installer:

   ```
   $ urlbase=http://cdimage.ubuntu.com/ubuntu-server/daily-live/current
   $ isoname=$(distro-info -d)-live-$(dpkg --print-architecture).iso
   $ zsync ${urlbase}/${isoname}.zsync
   ```

3. Run the provided script to make a copy of the downloaded installer
   that has your version of subiquity:

   ```
   $ sudo ./scripts/inject-subquity-snap.sh ${isoname} subquity_test.snap custom.iso
   ```

4. Boot the new iso in KVM:

   ```
   $ qemu-img create -f raw target.img 10G
   $ kvm -m 1024 -cdrom custom.iso -hda target.img -serial stdio
   ```

5. Finally, boot the installed image:

   ```
   $ kvm -m 1024 -hda target.img -serial stdio
   ```
