.. _cloudinit-autoinstall-interaction:

Cloud-init and autoinstall interaction
======================================

While cloud-init may provide the autoinstall configuration to the Ubuntu
installer, it does not process the autoinstall directives itself.

Cloud-init runs in both the ephemeral system (during installation) and in the target
system during first boot. Cloud-init then becomes inert for every subsequent
reboot.

To modify the ephemeral system with cloud-init, any
:external+cloud-init:ref:`#cloud-config module schema keys<modules>` can
be provided. If instead cloud-init directives are intended to modify the system
being installed, they must appear under a :ref:`ai-user-data` section under
``autoinstall:``.

.. code-block:: yaml

    #cloud-config
    # cloud-init directives may optionally be specified here.
    # These directives affect the ephemeral system performing the installation.

    autoinstall:
        # autoinstall directives must be specified here, not directly at the
        # top level.  These directives are processed by the Ubuntu Installer,
        # and configure the target system to be installed.

        user-data:
            # cloud-init directives may also be optionally be specified here.
            # These directives also affect the target system to be installed,
            # and are processed on first boot.

For an overview of the methods used to provide the autoinstall configuration to the Ubuntu installer, go to :ref:`Providing autoinstall configuration <providing-autoinstall>`.
