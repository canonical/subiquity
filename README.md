# subiquity
> Ubuntu Server Installer

# Acquiring the installer from PPA
 - Request access to https://launchpad.net/~subiquity
 - View your private PPA subscriptions: https://launchpad.net/~LP_USERID/+archivesubscriptions
 - Select subiquity-dev
 - Add your private ppa

`sudo apt-add-repository -y https://LPUSER:LPPASS@private-ppa.launchpad.net/subiquity/subiquity-dev/ubuntu`

`sudo apt-key adv --keyserver keyserver.ubuntu.com --recv 3D2F6C3B`

 - Update apt and install subiquity


`sudo apt-get update && sudo apt-get install subiquity`

 - Enable multiverse for UEFI testing in VM

`sudo apt-add-repository multiverse`

# Testing out the Text-UI (TUI)
SUbiquity's text UI is is available for testing without actually installing
anything to a system or a VM.  Subiquity developers make use of this for rapid
development.  After installing subiquity you can start it:

`subiquity --dry-run`

All of the features are present in dry-run mode.  The installer will emit it's
backend configuration files to /tmp/subiquity-config-* but it won't attempt to
run any installer commands (which would fail without root privileges).  Further,
subiquity can load other machine profiles in case you want to test out the
installer without having access to the machine.  A few sample machine
profiles are available in the package at /usr/share/subiquity/examples/ and
can be loaded via the --machine parameter:

`subiquity --dry-run \
           --machine /usr/share/subiquity/examples/desktop.json`

# Generating machine profiles
Machine profiles are generated from the probert tool.  This package is
also available in the Subiquity PPA.  To collect a machine profile:

`probert --all > mymachine.json`

# Acquire subiquity from source

`git clone https://github.com/CanonicalLtd/subiquity`

`cd subiquity && make install_deps`

# Running the UI locally in dry-run mode (no VM)

`make`

# Running the UI locally with a different machine profile (see examples/)

`MACHINE=examples/desktop.json make`

# Building installer image
The build system will generate a bootable image.  This image can be run inside
a VM, or copied to an USB disk and booted directly.

`make installer`

The resulting build image is avaiable at installer/installer.img  The installer
image requires approximately 2G of space at this time.

# Running installer locally in a VM

`make run`

# Overide default values for installer build

`make RELEASE=[wily, vivid, trusty] ARCH=[amd64, i386, armf, arm64, ppc64el] installer`

`make RELEASE=wily ARCH=arm64 run`
