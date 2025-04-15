.. _operate-server-installer:

Operating the server installer
==============================

This document explains how to use the installer in general terms. For a step-by-step guide through the screens of the installer, use the `screen-by-screen guide <https://discourse.ubuntu.com/t/screen-by-screen-installer-guide/16690>`_.

Get the installer
-----------------

Installer images are created (approximately) daily and are available from the `Ubuntu release <https://cdimage.ubuntu.com/ubuntu-server/daily-live/current/>`_ page. These images are not tested as extensively as the images from release days, but they contain the latest packages and installer. Therefore, fewer updates are required during or after installation.

Download the server installer for amd64 from the `Ubuntu Server <https://ubuntu.com/download/server>`_ page and other architectures from the `release directory <http://cdimage.ubuntu.com/releases/20.04/release/>`_.

Installer UI navigation
-----------------------

Use the :kbd:`↑` and :kbd:`↓` arrows, as well as the :kbd:`Space` or :kbd:`Enter` keys to navigate the installer.

:kbd:`Tab` and :kbd:`Shift` + :kbd:`Tab` move the focus down and up respectively. Use :kbd:`Home`, :kbd:`End`, :kbd:`PgUp` and :kbd:`PgDn` to navigate through long lists quickly.

Running the installer over a serial port
----------------------------------------

By default, the installer runs on the first virtual terminal, ``tty1``. This is what is displayed on any connected monitor by default. On systems without a monitor or a remote virtual terminal, you can run the installer on the serial port. To do this, specify an `appropriate console <https://www.kernel.org/doc/html/latest/admin-guide/serial-console.html>`_ on the kernel command line. A common value is ``console=ttyS0``.

When running on a serial port, the installer starts in a basic mode that uses only the ASCII character set and black and white colors. If you are connecting from a terminal emulator, such as gnome-terminal, that supports Unicode and rich colors, you can switch to "rich mode", which uses Unicode and colors, and supports
many languages.

.. _connect-via-ssh:

Connecting to the installer over SSH
------------------------------------

An alternative to basic terminals is to connect via SSH. If the network is up by the time the installer starts, instructions are offered on the initial screen in basic mode. Otherwise, instructions are available from the help menu once networking is configured.

In addition, connecting via SSH is capable of displaying all Unicode characters, which enables the use of more translations than can be displayed on a virtual terminal.

Help menu
---------

The help menu is in the top right of the screen. It contains help -- both general and for the currently displayed screen -- and some general actions.

Switching to a shell prompt
~~~~~~~~~~~~~~~~~~~~~~~~~~~

To switch to a shell at any time, select :guilabel:`Enter shell` from the help menu, or press :kbd:`Control` + :kbd:`Z` or :kbd:`F2`.

If you are accessing the installer via ``tty1``, you can also access a shell by switching to a different virtual terminal (:kbd:`Control` + :kbd:`Alt` + arrow, or :kbd:`Control` + :kbd:`Alt` + number keys, to move between virtual terminals).

Global keys
-----------

The following global keys work at any time:

====================================  =============================================
Key                                   Action
====================================  =============================================
:kbd:`Esc`                            Go back
:kbd:`F1`                             Open help menu
:kbd:`Control` + :kbd:`Z`, :kbd:`F2`  Switch to shell
:kbd:`Control` + :kbd:`L`, :kbd:`F3`  Redraw screen
:kbd:`Control` + :kbd:`T`, :kbd:`F4`  Toggle rich mode (color, Unicode) on and off
====================================  =============================================
