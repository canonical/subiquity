.. _operate-server-installer:

Operating the Server installer
******************************

This document explains how to use the installer in general terms. For a
step-by-step guide through the screens of the installer, you can use our
`screen-by-screen reference guide <https://discourse.ubuntu.com/t/screen-by-screen-installer-guide/16690>`_.

Get the installer
=================

Installer images are created (approximately) daily and are available from the
`Ubuntu release <https://cdimage.ubuntu.com/ubuntu-server/daily-live/current/>`_ page. These are not
tested as extensively as the images from release day, but they contain the
latest packages and installer, so fewer updates are required during or
after installation.

You can download the server installer for amd64 from the
`Ubuntu Server <https://ubuntu.com/download/server>`_ page and other architectures from the
`release directory <http://cdimage.ubuntu.com/releases/20.04/release/>`_.

Installer UI navigation
=======================

In general, the installer can be used with the :kbd:`up` and :kbd:`down` arrows
and :kbd:`space` or :kbd:`Enter` keys and a little typing. 

:kbd:`Tab` and :kbd:`Shift` + :kbd:`Tab` move the focus down and up respectively.
:kbd:`Home` / :kbd:`End` / :kbd:`Page Up` / :kbd:`Page Down` can be used to
navigate through long lists more quickly in the usual way.

Running the installer over a serial port
========================================

By default, the installer runs on the first virtual terminal, ``tty1``. This
is what is displayed on any connected monitor by default. However, servers do
not always have a monitor. Some out-of-band management systems provide a
remote virtual terminal, but sometimes it is necessary to run the installer on
the serial port. To do this, the kernel command line needs to
`have an appropriate console <https://www.kernel.org/doc/html/latest/admin-guide/serial-console.html>`_
specified on it -- a common value is ``console=ttyS0`` but this is not
something that can be generically documented.

When running on a serial port, the installer starts in a basic mode that uses only
the ASCII character set and black and white colours. If you are connecting from
a terminal emulator, such as gnome-terminal, that supports Unicode and rich
colours, you can switch to "rich mode" which uses Unicode and colours, and supports
many languages.

.. _connect-via-ssh:

Connecting to the installer over SSH
====================================

If the only available terminal is very basic, an alternative is to connect via
SSH. If the network is up by the time the installer starts, instructions are
offered on the initial screen in basic mode. Otherwise, instructions are
available from the help menu once networking is configured.

In addition, connecting via SSH is assumed to be capable of displaying all
Unicode characters, enabling more translations to be used than can be displayed
on a virtual terminal.

Help menu
=========

The help menu is always in the top right of the screen. It contains help --
both general and for the currently displayed screen -- and some general actions.

Switching to a shell prompt
---------------------------

You can switch to a shell at any time by selecting "Enter shell" from the help
menu, or pressing :kbd:`Control` + :kbd:`Z` or :kbd:`F2`.

If you are accessing the installer via ``tty1``, you can also access a shell
by switching to a different virtual terminal (:kbd:`Control` + :kbd:`Alt` +
arrow, or :kbd:`Control` + :kbd:`Alt` + number keys, to move between virtual
terminals).

Global keys
===========

There are some global keys you can press at any time:


====================================  =============================================
Key                                   Action
====================================  =============================================
:kbd:`Esc`                            Go back
:kbd:`F1`                             Open help menu
:kbd:`Control` + :kbd:`Z`, :kbd:`F2`  Switch to shell
:kbd:`Control` + :kbd:`L`, :kbd:`F3`  Redraw screen
:kbd:`Control` + :kbd:`T`, :kbd:`F4`  Toggle rich mode (colour, Unicode) on and off
====================================  =============================================
