.. _tutorial_intro-to-autoinstall:

Introduction to Autoinstall
***************************

Ubuntu installation automation is performed with the autoinstall format.
You might also know this feature as unattended or handsoff or preseeded
installation.

This format is supported in the following installers:
 * Ubuntu Server, version 20.04 and later
 * Ubuntu Desktop, version 23.04 and later

Autoinstallation lets you answer all those configuration questions ahead of
time with an *autoinstall config* and lets the installation process run without
any interaction.


Differences from debian-installer preseeding
============================================

*preseeds* are the way to automate an installer based on debian-installer
(also known as d-i).

Autoinstalls differ from preseeds in the following ways:
 * the format is different (yaml vs debconf-set-selections)
 * when the answer to a question is not present in a preseed, d-i stops and
   asks the user for input. Autoinstalls are not like this:  by default, if
   there is any autoinstall configuration at all, the installer takes the
   default for any unanswered question (and fails if there is no default).
 * You can designate particular sections in the configuration as "interactive",
   which means the installer will still stop and ask about those.


Providing the autoinstall configuration
=======================================

There are 2 methods of providing the autoinstall configuration:
 * Carried as part of cloud-config
 * Directly on the install media

Autoinstall by way of cloud-config
----------------------------------

The suggested method of providing autoinstall to the Ubuntu installer is by way
of cloud-init.  This allows the configuration to be applied to the installer
without having to modify the install media.

When providing autoinstall via cloud-init, the autoinstall config is wrapped in
a cloud-config header and an autoinstall top-level key, like so:

.. code-block:: yaml

    #cloud-config
    autoinstall:
        version: 1
        ....

Autoinstall on the install media
--------------------------------

Another option for supplying autoinstall to the Ubuntu installer is to place a
file named :code:`autoinstall.yaml` on the install media itself.

There are two potential locations for the :code:`autoinstall.yaml` file:
 * At the root of the "cdrom".  When writing the installation ISO to a USB
   Flash Drive, this can be done by copying the :code:`autoinstall.yaml` to the
   partition containing the contents of the ISO - i.e., in the same directory
   containing the :code:`casper` directory.
 * On the rootfs of the installation system - this option will typically
   require modifying the installation ISO and is not suggested, but is
   supported.

Directly specifying autoinstall as a :code:`autoinstall.yaml` file does not
require a :code:`#cloud-config` header, and does not use a top level
:code:`autoinstall` key.  The autoinstall directives are placed at the top
level.

.. code-block:: yaml

    version: 1
    ....


Cloud-init and Autoinstall interaction
======================================

While cloud-init may assist in providing the autoinstall configuration to the
Ubuntu installer, cloud-init itself is not processing the autoinstall.

If cloud-init directives are intended to modify the ephemeral system, they
must appear at the top level of the cloud-config.  If instead
cloud-init directives are intended to modify the system being installed, they
must appear under a :code:`user-data` section in :code:`autoinstall`.

.. code-block:: yaml

    #cloud-config
    # cloud-init directives may optionally be specified here.
    # These directives affect the ephemeral system performing the install.

    autoinstall:
        # autoinstall directives must be specified here, not directly at the
        # top level.  These directives are processed by the Ubuntu Installer,
        # and configure the target system to be installed.

        user-data:
            # cloud-init directives may also be optionally be specified here.
            # These directives also affect the target system to be installed,
            # and are processed on first boot.


Zero-touch deployment with autoinstall
======================================

The Ubuntu Installer contains a safeguard, intended to prevent USB Flash Drives
with an :code:`autoinstall.yaml` file from wiping out the wrong system.

During autoinstall, a prompt will be shown to confirm that the install really
should proceed and start making modifications to the target system. ::

    start: subiquity/Meta/status_GET
    Confirmation is required to continue.
    Add 'autoinstall' to your kernel command line to avoid this


    Continue with autoinstall? (yes|no)

To bypass this prompt, arrange for the argument :code:`autoinstall` to be
present on the kernel command line.


Creating an autoinstall config
==============================

When any system is installed using the Ubuntu installer, an autoinstall file
for repeating the install is created at
:code:`/var/log/installer/autoinstall-user-data`.


Error handling
==============

Progress through the installer is reported via the :ref:`ai-reporting` system,
including errors. In addition, when a fatal error occurs, the
:ref:`ai-error-commands` are executed and the traceback printed to the console.
The server then just waits.
