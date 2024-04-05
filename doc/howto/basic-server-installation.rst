Basic server installation
=========================

This chapter provides an overview of how to install Ubuntu Server Edition. See also the guide on :ref:`how to operate the installer <operate-server-installer>` for more information on using the installer, and the :ref:`screen-by-screen guide <screen-by-screen>` for more information about each of the installer screens.

Preparing to install
--------------------

This section explains various aspects to consider before starting the installation.

System requirements
~~~~~~~~~~~~~~~~~~~

Ubuntu Server Edition provides a common, minimalist base for a variety of server applications, such as file or print services, web hosting, email hosting, etc. This version supports four 64-bit architectures:

* amd64 (AMD64, Intel 64)
* arm64 (AArch64)
* ppc64el (POWER8 and POWER9)
* s390x (IBM Z and LinuxONE)

Recommended system requirements:

* CPU: 1 GHz or better
* RAM: 1 GB or more
* Disk: 2.5 GB or more

Perform a system backup
~~~~~~~~~~~~~~~~~~~~~~~

Before installing Ubuntu Server Edition, back up all system data.

.. warning:: Power failures, configuration mistakes, and other problems occurring during disk (re-)partitioning can result in complete data loss. Always back up your data before performing an installation of a new system.

Download the Server ISO
~~~~~~~~~~~~~~~~~~~~~~~

Download the amd64 Server Edition from `releases.ubuntu.com <https://releases.ubuntu.com/>`_. Choose the version to install and select the :guilabel:`Server install image` download. Note that the Server download includes the installer.

There are platform-specific how-to guides for installations on:

* `s390x LPAR <https://discourse.ubuntu.com/t/interactive-live-server-installation-on-ibm-z-lpar-s390x/16601>`_
* `z/VM <https://discourse.ubuntu.com/t/interactive-live-server-installation-on-ibm-z-vm-s390x/16604>`_
* `ppc64el <https://discourse.ubuntu.com/t/using-a-virtual-cdrom-and-petitboot-to-start-a-live-server-installation-on-ibm-power-ppc64el/16694>`_

Create a bootable USB
~~~~~~~~~~~~~~~~~~~~~

There are many ways to boot the installer but the simplest and most common way is to `create a bootable USB stick <https://ubuntu.com/tutorials/create-a-usb-stick-on-ubuntu>`_ (`tutorials for other operating systems <https://ubuntu.com/search?q=%22create+a+bootable+USB+stick%22>`_ are also available).

Perform the installation
------------------------

Now that you have prepared your installation medium, you are ready to install.

Boot the installer
~~~~~~~~~~~~~~~~~~

Plug the USB stick into the system to be installed and (re)start it.

Many computers automatically boot from available USB or DVD media. If you don't see the boot message and
the :guilabel:`Welcome` screen, set your computer to boot from the installation media.

.. note:: See your computer manual for instructions on how to select the boot source. You can also watch the screen during computer (re)start for a message with what key to press to access settings or a boot menu. Depending on the manufacturer, this can be :kbd:`Escape`, :kbd:`Enter`, :kbd:`F2`, :kbd:`F10` or :kbd:`F12`. Restart your computer and hold down this key until the boot menu appears, then select the drive with the Ubuntu installation medium. See also `Ubuntu Community documentation on booting from CD/DVD <https://help.ubuntu.com/community/BootFromCD>`_.

After a few moments, the installer starts in its language selection screen.

.. image:: figures/basic-installation-start-screen.png
   :alt: Welcome screen of the Server installer showing the language selection options

Using the installer
~~~~~~~~~~~~~~~~~~~

The installer is designed to be easy to use and have sensible default settings. For a first installation, you can accept the defaults:

#. Choose your language.
#. Update the installer (if offered).
#. Select your keyboard layout.
#. Do not configure networking (the installer attempts to configure wired network interfaces via DHCP, but you can continue without networking if this fails).
#. Do not configure a proxy or custom mirror unless you have to in your network.
#. For storage, leave :guilabel:`Use an entire disk` checked, and choose a disk to install to, then select :guilabel:`Done` on the configuration screen and confirm the installation.
#. Enter a username, hostname and password.
#. On the :guilabel:`SSH Setup` and :guilabel:`Featured Server Snaps` screens, select :guilabel:`Done`.
#. You now see log messages as the installation is completed.
#. Select :guilabel:`Reboot` when this is complete, and log in using the username and password provided.
