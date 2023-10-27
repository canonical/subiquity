.. _autoinstall_quick-start:

Autoinstall quick start
=======================

This guide provides instructions on how to use autoinstall with a current version of Ubuntu for the amd64 architecture in a virtual machine (VM) on your computer.

For older Ubuntu releases, substitute the version in the name of the ISO image. The instructions should otherwise be the same. See :ref:`<autoinstall-quick-start-s390x>` for instructions on installing on the s390x architecture.

Providing the autoinstall data over the network
-----------------------------------------------

This method describes a network-based installation. When booting over a network, use this method to deliver autoinstall to perform the installation.

Download the ISO
~~~~~~~~~~~~~~~~

Download the latest release of the Ubuntu Server image (ISO) from the `Ubuntu ISO download page`_ (currently |ubuntu-latest-version| (|ubuntu-latest-codename|)).

Mount the ISO
~~~~~~~~~~~~~

Make the content of the ISO image accessible from a local directory:

.. code:: none

    sudo mount -r ~/Downloads/ubuntu-<version-number>-live-server-amd64.iso /mnt

Change ``<version-number>`` to match the number of the release you have downloaded.

Write your autoinstall configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Create a cloud-init configuration:

.. code:: none

    mkdir -p ~/www
    cd ~/www
    cat > user-data << 'EOF'
    #cloud-config
    autoinstall:
    version: 1
    identity:
        hostname: ubuntu-server
        password: "$6$exDY1mhS4KUYCE/2$zmn9ToZwTKLhCw.b4/b.ZRTIZM30JZ4QrOQ2aOXJ8yk96xpcCof0kxKwuX1kqLG/ygbJ1f8wxED22bTL4F46P0"
        username: ubuntu
    EOF
    touch meta-data

The encrypted password is ``ubuntu``.

Serve the cloud-init configuration over HTTP
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Leave the HTTP server running in a terminal:

.. code:: none

    cd ~/www
    python3 -m http.server 3003

Create a target disk
~~~~~~~~~~~~~~~~~~~~

Create the target VM disk for the installation:

.. code:: none

    truncate -s 10G image.img

Run the installation
~~~~~~~~~~~~~~~~~~~~

Change ``<version-number>`` in the following command to match the release ISO you downloaded.

.. code:: none

    kvm -no-reboot -m 2048 \
        -drive file=image.img,format=raw,cache=none,if=virtio \
        -cdrom ~/Downloads/ubuntu-<version-number>-live-server-amd64.iso \
        -kernel /mnt/casper/vmlinuz \
        -initrd /mnt/casper/initrd \
        -append 'autoinstall ds=nocloud-net;s=http://_gateway:3003/'

This command boots the VM, downloads the configuration from the server (prepared in the previous step) and runs the installation. The installer reboots at the end. The ``-no-reboot`` option to the ``kvm`` command instructs ``kvm`` to exit on reboot.

Boot the installed system
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: none

    kvm -no-reboot -m 2048 \
        -drive file=image.img,format=raw,cache=none,if=virtio

This command boots the installed system in the VM. Log in using ``ubuntu`` for both the user name and password.

Using another volume to provide the autoinstall configuration
-------------------------------------------------------------

Use this method to create an installation medium to plug into a computer to have it be installed.

Download the ISO
~~~~~~~~~~~~~~~~

Download the latest Ubuntu Server ISO from the `Ubuntu ISO download page`_.

Create user-data and meta-data files
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: none

    mkdir -p ~/cidata
    cd ~/cidata
    cat > user-data << 'EOF'
    #cloud-config
    autoinstall:
    version: 1
    identity:
        hostname: ubuntu-server
        password: "$6$exDY1mhS4KUYCE/2$zmn9ToZwTKLhCw.b4/b.ZRTIZM30JZ4QrOQ2aOXJ8yk96xpcCof0kxKwuX1kqLG/ygbJ1f8wxED22bTL4F46P0"
        username: ubuntu
    EOF
    touch meta-data

The encrypted password is ``ubuntu``.

Create an ISO to use as a cloud-init data source
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Install utilities for working with cloud images:

.. code:: none

    sudo apt install cloud-image-utils

Create the ISO image for cloud-init:

.. code:: none

    cloud-localds ~/seed.iso user-data meta-data

Create a target disk
~~~~~~~~~~~~~~~~~~~~

Create the target VM disk for the installation:

.. code:: none

    truncate -s 10G image.img

Run the installation
~~~~~~~~~~~~~~~~~~~~

Change ``<version-number>`` in the following command to match the release ISO you downloaded.

.. code:: none

    kvm -no-reboot -m 2048 \
        -drive file=image.img,format=raw,cache=none,if=virtio \
        -drive file=~/seed.iso,format=raw,cache=none,if=virtio \
        -cdrom ~/Downloads/ubuntu-<version-number>-live-server-amd64.iso

This command boots the system and runs the installation. The installer prompts for a confirmation before modifying the disk. To skip the need for a confirmation, interrupt the booting process, and add the ``autoinstall`` parameter to the kernel command line.

The installer reboots at the end. The ``-no-reboot`` option to the ``kvm`` command instructs ``kvm`` to exit on reboot.

Boot the installed system
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: none

    kvm -no-reboot -m 2048 \
        -drive file=image.img,format=raw,cache=none,if=virtio

This command boots the installed system in the VM. Log in using ``ubuntu`` for both the user name and password.

.. LINKS

.. _Ubuntu ISO download page: https://releases.ubuntu.com/
