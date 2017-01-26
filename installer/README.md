Getting Started
---------------

Grab a copy of curtin (for some conversion tools):

    sudo apt-get install bzr
    mkdir -p ~/download
    cd ~/download
    bzr branch lp:curtin

Create the image
----------------

Generate the install image from subiquity's root directory:

    installer/geninstaller -a amd64 -b grub2 -r zesty -l

(-l means build the current working tree into a deb and install that,
leaving it out will install subiquity from the archive).

Run the installer
-----------------

    # generate target device
    qemu-img create -f raw target.img 10G

    # run installer
    sudo qemu-system-x86_64 -m 1024 -enable-kvm \
         -hda installer.img -hdb target.img \
         -serial telnet:127.0.0.1:2445,server,nowait \
         -monitor stdio

Boot the installed image
------------------------

    sudo qemu-system-x86_64 -m 1024 -enable-kvm \
         -hda target.img \
         -serial telnet:127.0.0.1:2445,server,nowait

