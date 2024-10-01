.. _security-overview

Security overview
=================

This explanation covers several security related topics for the Subiquity and
Ubuntu-desktop-bootstrap installation ISOs.


About the installer user
------------------------

At installation time, the default user should be considered to have root
privileges.  The install system must be able to make arbitrary changes to the
target system so that the install can complete successfully.  Additionally,
there is an ``/etc/sudoers.d`` ``NOPASSWD`` entry for the default user, which
means that the default installer user can become root at any time with a
``sudo`` invocation.


Ubuntu-server ISO has listening by default with a random password
-----------------------------------------------------------------

The Ubuntu Server ISO offers SSH access to the installation system, to
facilitate installs which need to start over a minimal serial line that may not
be rich enough to run the installer user interface.  In that case, the SSH
access information is printed on that serial line.

Additionally, from the Subiquity UI, one can see the SSH access info by
navigating to the Help Menu -> Help on SSH Access.

.. image:: figures/ssh-info.png
   :alt: Help on SSH Access

Note that a default password is never used, that instead a 20 character random
password is generated and is unique to that given boot of the installer.

Ubuntu Desktop and Ubuntu flavours do not have the SSH server installed by
default.


Security updates are installed if Ubuntu archive access is available
--------------------------------------------------------------------

One of the last steps performed by the Subiquity and Ubuntu-desktop-bootstrap
installers is to use ``unattended-upgrades`` to apply updates to the target
system.  Security updates are always applied, if the installer has network
access to the Ubuntu archive.  Optionally, non-security updates can be
configured to be applied before first boot when using ``autoinstall``
:ref:`ai-updates` with the value ``all``.


Details on Encrypted installations
----------------------------------

LVM
^^^

To implement full disk encryption in the style referred to as "LVM", 3
partitions are created:

1. A bootloader partition
2. An ``ext4`` partition mounted at ``/boot``
3. A partition used as the :manualpage:`cryptsetup(8) <man5/keyboard.5.html>`
   device.  The resulting LUKS encrypted block device is then used as the LVM
   Volume Group physical device, and the rootfs is created in a logical volume.

The configured passphrase is then used to unlock the LUKS encrypted device.

Note that while the term "full disk encryption" is used, ``/boot`` and any data
on the bootloader partition remain unencrypted in this scheme.

ZFS
^^^

ZFS disk encryption in Subiquity and Ubuntu-desktop-installer is a hybrid of
LUKS and ZFS encryption approaches.  In addition to the required bootloader
partition, two pools ``bpool`` and ``rpool`` are created.

* A LUKS device is created as a ZFS dataset in the ``rpool``.
* The configured passphrase is used to encrypt the LUKS device.
* The real key for the ZFS dataset is contained in the "keystore" LUKS device
  as a simple file.
* The ``rpool`` is decrypted using this simple file inside the encrypted LUKS
  device.
