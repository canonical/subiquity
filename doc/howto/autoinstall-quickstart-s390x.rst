.. _autoinstall-quickstart-s390x:

Automatic installation quick start for s390x
********************************************

This how-to provides basic instructions to perform an automatic installation
in a virtual machine (VM) on a local machine on the s390x architecture.

This how-to is a version of :ref:`autoinstall_quickstart`.
adapted for s390x.

Download an ISO
===============

At the time of writing (just after the Kinetic release), the best place to go
is here:
https://cdimage.ubuntu.com/ubuntu/releases/22.10/release/

..code-block:: bash

    wget https://cdimage.ubuntu.com/ubuntu/releases/22.10/release/ubuntu-22.10-live-server-s390x.iso -P ~/Downloads

Mount the ISO
=============

.. code-block:: bash

    mkdir -p ~/iso
    sudo mount -r ~/Downloads/ubuntu-22.10-live-server-s390x.iso ~/iso

Write your autoinstall config
=============================

Create a cloud-init configuration:

.. code-block:: none

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

The crypted password is ``ubuntu``.

Serve the cloud-init config over HTTP
=====================================

Leave this running in one terminal window:

.. code-block:: none

    cd ~/www
    python3 -m http.server 3003

Create a target disk
====================

Proceed with a second terminal window:

.. code-block:: none

    sudo apt install qemu-utils
    ...

    qemu-img create -f qcow2 disk-image.qcow2 10G
    Formatting 'disk-image.qcow2', fmt=qcow2 size=10737418240 cluster_size=65536 lazy_refcounts=off refcount_bits=16

    qemu-img info disk-image.qcow2
    image: disk-image.qcow2
    file format: qcow2
    virtual size: 10 GiB (10737418240 bytes)
    disk size: 196 KiB
    cluster_size: 65536
    Format specific information:
        compat: 1.1
        lazy refcounts: false
        refcount bits: 16
        corrupt: false

Run the installation
====================

.. code-block:: none

    sudo apt install qemu-kvm
    ...

Add the default user to the ``kvm`` group:

.. code-block:: none

    sudo usermod -a -G kvm ubuntu   # re-login to make the changes take effect

    kvm -no-reboot -name auto-inst-test -nographic -m 2048 \
        -drive file=disk-image.qcow2,format=qcow2,cache=none,if=virtio \
        -cdrom ~/Downloads/ubuntu-22.10-live-server-s390x.iso \
        -kernel ~/iso/boot/kernel.ubuntu \
        -initrd ~/iso/boot/initrd.ubuntu \
        -append 'autoinstall ds=nocloud-net;s=http://_gateway:3003/ console=ttysclp0'

The above commands boot the virtual machine, download the configuration from the server
(prepared in the previous step) and run the installation.

The installer reboots at the end. The ``-no-reboot`` flag to ``kvm`` instructs ``kvm``
to terminate on reboot. The procedure takes approximately 5 minutes.

Boot the installed system
=========================

.. code-block:: none

    kvm -no-reboot -name auto-inst-test -nographic -m 2048 \
        -drive file=disk-image.qcow2,format=qcow2,cache=none,if=virtio

This command boots into the installed system. Log in using ``ubuntu`` for both the user
name and password.
