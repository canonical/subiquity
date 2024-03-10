.. _autoinstall_quick_start_s390x:

Autoinstall quick start for s390x
=================================

This guide provides instructions on how to use autoinstall with a current version of Ubuntu for the s390x architecture in a virtual machine (VM) on your computer.

For older Ubuntu releases, substitute the version in the name of the ISO image. The instructions should otherwise be the same. See :ref:`Autoinstall quick start<autoinstall_quick_start>` for instructions on installing on the amd64 architecture.

Download the ISO
----------------

Download the latest release of the Ubuntu Server image (ISO) from the `Ubuntu ISO download page`_ (currently |ubuntu-latest-version| (|ubuntu-latest-codename|)).

Mount the ISO
-------------

Make the content of the ISO image accessible from a local directory:

.. code:: none

    mkdir -p ~/iso
    sudo mount -r ~/Downloads/ubuntu-<version-number>-live-server-s390x.iso ~/iso

Change ``<version-number>`` to match the number of the release you have downloaded.

Write your autoinstall configuration
------------------------------------

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

The encrypted password is ``ubuntu``.

Serve the cloud-init configuration over HTTP
--------------------------------------------

Leave the HTTP server running in a terminal:

.. code-block:: none

    cd ~/www
    python3 -m http.server 3003

Create a target disk
--------------------

In a new terminal, install the ``qemu-img`` utility:

.. code-block:: none

    sudo apt install qemu-utils
    ...

Create the target VM disk for the installation:

.. code-block:: none

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
--------------------

Install the ``kvm`` command:

.. code-block:: none

    sudo apt install qemu-kvm
    ...

Add the default user to the ``kvm`` group:

.. code-block:: none

    sudo usermod -a -G kvm ubuntu   # re-login to make the changes take effect

Run the installation in a VM. Change ``<version-number>`` in the following command to match the release ISO you downloaded:

.. code-block:: none

    kvm -no-reboot -name auto-inst-test -nographic -m 2048 \
        -drive file=disk-image.qcow2,format=qcow2,cache=none,if=virtio \
        -cdrom ~/Downloads/ubuntu-<version-number>-live-server-s390x.iso \
        -kernel ~/iso/boot/kernel.ubuntu \
        -initrd ~/iso/boot/initrd.ubuntu \
        -append 'autoinstall ds=nocloud-net;s=http://_gateway:3003/ console=ttysclp0'

This command boots the VM, downloads the configuration from the server (prepared in the previous step) and runs the installation. The installer reboots at the end. The ``-no-reboot`` option to the ``kvm`` command instructs ``kvm`` to exit on reboot.

Boot the installed system
-------------------------

.. code-block:: none

    kvm -no-reboot -name auto-inst-test -nographic -m 2048 \
        -drive file=disk-image.qcow2,format=qcow2,cache=none,if=virtio

This command boots the installed system in the VM. Log in using ``ubuntu`` for both the user name and password.

.. LINKS

.. _Ubuntu ISO download page: https://releases.ubuntu.com/
