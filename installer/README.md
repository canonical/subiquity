Getting Started
---------------

Install package dependencies:

    PKGS="
    bzr
    extlinux
    gdisk
    kpartx
    parted
    qemu-system-x86
    qemu-utils
    syslinux-common
    ubuntu-cloudimage-keyring
    cloud-image-utils
    grub-pc-bin
    "
    apt-get install $PKGS

Grab a copy of curtin (for some conversion tools):

    mkdir -p ~/download
    cd ~/download
    bzr branch lp:curtin

Generate the install image from subiquity's root directory:

    installer/geninstaller.sh -a amd64 -b grub2 -r zesty


Run the installer

    # generate target device
    qemu-img create -f raw target.img 10G

    # run installer
    sudo qemu-system-x86_64 -m 1024 -enable-kvm \
         -hda installer.img -hdb test.img \
         -serial telnet:127.0.0.1:2445,server,nowait \
         -monitor stdio

    # login and shutdown, ubuntu/passw0rd


Boot the installed image

    sudo qemu-system-x86_64 -m 1024 -enable-kvm \
         -hda test.img \
         -serial telnet:127.0.0.1:2445,server,nowait

