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

To try out your changes for real, it is necessary to install them into an
image. See the comments in scripts/inject-subiquity-snap.sh for how to do this.
