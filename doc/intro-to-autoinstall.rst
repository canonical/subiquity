.. _tutorial_intro-to-autoinstall:

Introduction to autoinstall
===========================

Automatic Ubuntu installation is performed with the autoinstall format.
You might also know this feature as "unattended", "hands-off" or "preseeded"
installation.

This format is supported in the following installers:
 * Ubuntu Server, version 20.04 and later
 * Ubuntu Desktop, version 23.04 and later

Automatic installation lets you answer all configuration questions ahead of
time with an *autoinstall configuration* and lets the installation process run without
any interaction.

For more details on the relationship between autoinstall and cloud-init, as well as their respective functions, go to:

* :ref:`Cloud-init and autoinstall interaction <cloudinit-autoinstall-interaction>`
* :ref:`Providing autoinstall configuration <providing-autoinstall>`


Differences from `debian-installer` preseeding
----------------------------------------------

*preseeds* are the way to automate an installer based on `debian-installer`
(also known as d-i).

Autoinstalls differ from preseeds in the following ways:
 * The format is different: autoinstalls use YAML instead of the preseed
   debconf-set-selections.
 * When the answer to a question is not present in a preseed, d-i stops and
   asks the user for input. By comparison, if there is any autoinstall
   configuration at all, the autoinstall takes the default for any
   unanswered question (and fails if there is no default).
 * You can designate particular sections in the autoinstall configuration as
   "interactive", which means the installer will still stop and ask about
   those.


Error handling
--------------

Progress through the installer is reported via the :ref:`ai-reporting` system,
including errors. In addition, when a fatal error occurs, the
:ref:`ai-error-commands` are executed and the traceback printed to the console.
The server then just waits.
