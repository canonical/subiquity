.. _screen-by-screen:

Screen-by-screen installer walk-through
=======================================

The installer is designed to be easy to use without documentation. This guide provides more information on each of the screens of the installer to guide you through an installation.

Language selection
------------------

.. image:: figures/sbs-language.png
   :alt: Welcome!

This screen lets you select the language for the installer and the default language for the installed system. In case only a basic terminal with limited language support is available for the installation, an alternative is to :ref:`connect via SSH <connect-via-ssh>`.

Refresh
-------

.. image:: figures/sbs-refresh.png
   :alt: Installer update available

This screen is shown if there is an update available for the installer. Update the installer to get any improvements and bug fixes made since the release.

If you choose to update, the new version is downloaded, and the installer will restart at the same point of the installation.

Keyboard
--------

.. image:: figures/sbs-keyboard.png
   :alt: Keyboard configuration

Choose the layout and variant of keyboard attached to the system, if any. When running in a virtual terminal, it is possible to guess the layout and variant by answering questions about the keyboard. Select :guilabel:`Identify keyboard` to use this feature.

Zdev (s390x only)
-----------------

.. code-block::

    ====================================================================
      Zdev setup                                                      
    ====================================================================
      ID                          ONLINE  NAMES                                  ^
                                                                                 │
      generic-ccw                                                                │
      0.0.0009                                    >                              │
      0.0.000c                                    >                              │
      0.0.000d                                    >                              │
      0.0.000e                                    >                              │
                                                                                 │
      dasd-eckd                                                                  │
      0.0.0190                                    >                              │
      0.0.0191                                    >                              │
      0.0.019d                                    >                              │
      0.0.019e                                    >┌────────────┐
      0.0.0200                                    >│< (close)   │
      0.0.0300                                    >│  Enable    │
      0.0.0400                                    >│  Disable   │
      0.0.0592                                    >└────────────┘                v

                                     [ Continue   ]
                                     [ Back       ]

This screen is only shown on the s390x architecture and allows z-specific configuration of devices.

The list of devices can be long. Use the :kbd:`Home`, :kbd:`End`, :kbd:`PgUp` and :kbd:`PgDn` keys navigate through the list quickly.

Network
-------

.. image:: figures/sbs-network.png
   :alt: Network connections

This screen allows the configuration of the network. Ubuntu Server uses Netplan to configure networking and the installer can configure a subset of Netplan capabilities. In particular, it can configure DHCP or static
addressing, VLAN and bonds.

If networking is present (defined as "at least one interface has a default route"), then the installer installs updates from the repository at the end of installation.

Proxy
-----

.. image:: figures/sbs-proxy.png
   :alt: Configure proxy

Use this screen to configure proxy for accessing the package repository and the snap store both in the installer environment and in the installed system.

Mirror
------

.. image:: figures/sbs-mirror.png
   :alt: Configure Ubuntu archive mirror

The installer attempts to use geolocation to find an appropriate default package mirror for your location. To use a different mirror, enter its URL here.

Storage
-------

.. image:: figures/sbs-storage.png
   :alt: Storage configuration

Storage configuration is a complex topic and :ref:`has its own page for documentation <configure-storage>`.

.. image:: figures/sbs-confirm-storage.png
   :alt: Storage configuration

Once the storage configuration is confirmed, the installation begins in the background.

Identity
--------

.. image:: figures/sbs-identity.png
   :alt: Profile setup

The default user will be an administrator who can use ``sudo`` (this is why a password is needed, even if SSH public-key access is enabled on the next screen).

SSH
---

.. image:: figures/sbs-ssh.png
   :alt: SSH Setup

A default Ubuntu installation has no open ports. As it is very common to administer servers via SSH, the installer allows it to be installed.

You can import keys for the default user from GitHub or Launchpad.

If you import a key, then password authentication is disabled by default. It can be re-enabled later.

Snaps
-----

.. image:: figures/sbs-snaps.png
   :alt: Featured Server Snaps

If a network connection is enabled, a selection of snaps that are useful in a server environment is presented and can be selected for installation.

Installation logs
-----------------

.. image:: figures/sbs-logs.png
   :alt: Installing system

The final screen of the installer shows the progress of the installer and allows viewing of the full log file. Once the installation has completed and security updates have been installed, the installer waits for a confirmation before restarting.

.. image:: figures/sbs-complete.png
   :alt: Installation complete
