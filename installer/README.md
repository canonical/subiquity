Getting Started
---------------

Install package dependencies:

    PKGS="
    bzr
    qemu-system-x86
    qemu-utils
    grub-pc-bin
    "
    apt-get install $PKGS

Grab a copy of curtin (for some conversion tools):

    mkdir -p ~/download
    cd ~/download
    bzr branch lp:curtin

Generate the install image from subiquity's root directory:

    installer/geninstaller -a amd64 -b grub2 -r zesty
    mv ~/download/maas/daily/*/amd64/*/installer.img .

Run the installer

    # generate target device
    qemu-img create -f raw target.img 10G

    # run installer
    sudo qemu-system-x86_64 -m 1024 -enable-kvm \
         -hda installer.img -hdb target.img \
         -serial telnet:127.0.0.1:2445,server,nowait \
         -monitor stdio

    # login and shutdown, ubuntu/passw0rd


Boot the installed image

    sudo qemu-system-x86_64 -m 1024 -enable-kvm \
         -hda target.img \
         -serial telnet:127.0.0.1:2445,server,nowait

