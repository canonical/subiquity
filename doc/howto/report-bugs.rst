.. _report-bugs:

Troubleshooting
===============

This section explains how to deal with installation problems and how to report issues to the Subiquity team.

Update Subiquity
----------------

Ensure you're using the latest stable version of the installer. Update the Subiquity snap by running ``snap refresh``.

Crash reports
-------------

A failure results in a crash report being generated in ``/var/crash`` in the installer environment. The crash report includes all information for failure diagnostics. Starting with Ubuntu 19.10, crash reports are saved to the installation medium by default (provided there is enough space).

When an error occurs, the installer displays a dialog for uploading the report to the error tracker and offers options for continuing. Uploads to the error tracker are non-interactive and anonymous. This is useful for
tracking which kinds of errors affect most users.

Create a Launchpad bug report
-----------------------------

To create a Launchpad bug report based on the contents of a crash report, use the ``apport-cli`` tool that is part of Ubuntu. Copy the crash report to another system, and follow the prompts after executing:

.. code-block:: bash

    apport-cli /path/to/report.crash

To run ``apport-cli`` in the installer environment, switch to a shell. This way, ``apport`` can not open a browser to for you to complete the report. Instead, it provides a URL for completing the report, which you can do on another computer.

.. note::

Issues for the Subiquity autoinstaller are `tracked in Launchpad <https://bugs.launchpad.net/subiquity>`_.
