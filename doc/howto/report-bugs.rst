.. _report-bugs:

How to report a problem
***********************

We always hope, of course, that every installation with the server installer
succeeds. But reality doesn't always work that way and there will sometimes be
failures of various kinds. This section explains the most useful way to report
any failures so that we can fix the bugs causing them, and we'll keep the topic
up to date as the installer changes.

Update Subiquity
================

The first thing to do is to update your Subiquity snap using `snap refresh`.
Not only because we fix issues that cause failures over time but also because
we've been working on features to make failure reporting easier.

Crash reports
=============

A failure will result in a crash report being generated which bundles up all
the information we need to fully diagnose a failure. These live in
``/var/crash`` in the installer environment, and for Ubuntu 19.10 and newer
this is persisted to the installation media by default (if there is space).

When an error occurs you are presented with a dialog that allows you to upload
the report to the error tracker and offers options for continuing. Uploads to
the error tracker are non-interactive and anonymous, so they are useful for
tracking which kinds of errors are affecting most users, but they do not give
us a way to ask you to help diagnose the failure.

Create Launchpad bug report
===========================

You can create a Launchpad bug report, which lets us establish this kind
of two way communication, based on the contents of a crash report by using the
standard ``apport-cli`` tool that is part of Ubuntu. Copy the crash report to
another system, run:

.. code-block:: bash

    apport-cli /path/to/report.crash

and follow the prompts.

You can also run ``apport-cli`` in the installer environment by switching to a
shell but ``apport`` won't be able to open a browser to allow you to complete
the report so you'll have to type the URL by hand on another machine.

.. note::

   Bugs for the Subiquity autoinstaller are `tracked in Launchpad <https://bugs.launchpad.net/subiquity>`_.



