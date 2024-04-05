Zero-touch deployment with autoinstall
======================================

The Ubuntu Installer contains a safeguard, intended to prevent USB Flash Drives
with an :code:`autoinstall.yaml` file from wiping out the wrong system.

Before the Ubuntu Installer actually makes changes to the target system, a
prompt is shown. ::

    start: subiquity/Meta/status_GET
    Confirmation is required to continue.
    Add 'autoinstall' to your kernel command line to avoid this


    Continue with autoinstall? (yes|no)

To bypass this prompt, arrange for the argument :code:`autoinstall` to be
present on the kernel command line.
