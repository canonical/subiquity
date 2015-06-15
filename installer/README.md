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
    "
    apt-get install $PKGS

Generate the install image

    ./geninstaller.sh


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

