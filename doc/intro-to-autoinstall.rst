.. _tutorial_intro-to-autoinstall:

Introduction to autoinstall
***************************

Automatic Ubuntu installation is performed with the autoinstall format.
You might also know this feature as "unattended", "hands-off" or "preseeded"
installation.

This format is supported in the following installers:
 * Ubuntu Server, version 20.04 and later
 * Ubuntu Desktop, version 23.04 and later

Automatic installation lets you answer all those configuration questions ahead of
time with an *autoinstall configuration* and lets the installation process run without
any interaction.


Differences from `debian-installer` preseeding
==============================================

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


Providing the autoinstall configuration
=======================================

There are 2 ways to provide the autoinstall configuration:
 * Provide :external+cloud-init:ref:`#cloud-config user data <user_data_formats-cloud_config>` containing ``autoinstall:``
   configuration directives to cloud-init at boot time
 * Directly on the installation media

Autoinstall by way of `cloud-config`
------------------------------------

The suggested way of providing autoinstall configuration to the Ubuntu installer is
via cloud-init. This allows the configuration to be applied to the installer
without having to modify the installation media.

The autoinstall configuration is provided via cloud-init configuration, which is
almost endlessly flexible. In most scenarios the easiest way will be to provide
user data via the :external+cloud-init:ref:`datasource_nocloud` data source.

When providing autoinstall via cloud-init, the autoinstall configuration is provided
as :external+cloud-init:ref:`user_data_formats-cloud_config`. This
means we need a :code:`#cloud-config` header. The autoinstall directives are
placed under a top level :code:`autoinstall:` key, like so:

.. code-block:: yaml

    #cloud-config
    autoinstall:
        version: 1
        ....

.. note::

   :external+cloud-init:ref:`user_data_formats-cloud_config` files must contain
   the ``#cloud-config`` header to be recognised as a valid cloud configuration data
   file.

Autoinstall on the installation media
-------------------------------------

Another option for supplying autoinstall to the Ubuntu installer is to place a
file named :code:`autoinstall.yaml` on the installation media itself.

There are two potential locations that Subiquity will check for the
:code:`autoinstall.yaml` file:

* At the root of the "CD-ROM". When you write the installation ISO to a USB
  Flash Drive, this can be done by copying the :code:`autoinstall.yaml` to the
  partition containing the contents of the ISO - i.e.,
  in the directory containing the ``casper`` sub-directory.
* On the rootfs of the installation system - this option will typically
  require modifying the installation ISO and is not suggested, but is
  supported.

Alternatively, you can pass the location of the autoinstall file on the kernel
command line via the :code:`subiquity.autoinstallpath` parameter, where the
path is relative to the rootfs of the installation system. For example:

* :code:`subiquity.autoinstallpath=path/to/autoinstall.yaml`


Order precedence of the autoinstall locations
=============================================

Since there are many ways to specify the autoinstall file, it may happen that
multiple locations are specified at once. Subiquity will look for the
autoinstall file in the following order and pick the first existing one:

1. Kernel command line
2. Root of the installation system
3. `cloud-config`
4. Root of the CD-ROM (ISO)


Cloud-init and autoinstall interaction
======================================

Cloud-init runs in both the ephemeral system (during installation) and in the target
system during first boot. Cloud-init then becomes inert for every subsequent
reboot.

While cloud-init may provide the autoinstall configuration to the Ubuntu
installer, it does not process the autoinstall directives itself.

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


Creating an autoinstall configuration
=====================================

When any system is installed using the Ubuntu installer, an autoinstall file
for repeating the installation is created at
:code:`/var/log/installer/autoinstall-user-data`.


The structure of an autoinstall configuration
=============================================

See the :ref:`ai` for full details on the supported autoinstall directives.

A minimal autoinstall configuration in
:external+cloud-init:ref:`user_data_formats-cloud_config` format looks like:

.. code-block:: yaml

    #cloud-config
    autoinstall:
        version: 1
        identity:
            hostname: hostname
            username: username
            password: $crypted_pass

Here is an example file that shows off most of the autoinstall directives:

.. parsed-literal::

    #cloud-config
    autoinstall:
        :ref:`ai-version`: 1
        :ref:`ai-reporting`:
            hook:
                type: webhook
                endpoint: http\://example.com/endpoint/path
        :ref:`ai-early-commands`:
            - ping -c1 198.162.1.1
        :ref:`ai-locale`: en_US
        :ref:`ai-keyboard`:
            layout: gb
            variant: dvorak
        :ref:`ai-network`:
            network:
                version: 2
                ethernets:
                    enp0s25:
                       dhcp4: yes
                    enp3s0: {}
                    enp4s0: {}
                bonds:
                    bond0:
                        dhcp4: yes
                        interfaces:
                            - enp3s0
                            - enp4s0
                        parameters:
                            mode: active-backup
                            primary: enp3s0
        :ref:`ai-proxy`: http\://squid.internal:3128/
        :ref:`ai-apt`:
            primary:
                - arches: [default]
                  uri: http\://repo.internal/
            sources:
                my-ppa.list:
                    source: "deb http\://ppa.launchpad.net/curtin-dev/test-archive/ubuntu $RELEASE main"
                    keyid: B59D 5F15 97A5 04B7 E230  6DCA 0620 BBCF 0368 3F77
        :ref:`ai-storage`:
            layout:
                name: lvm
        :ref:`ai-identity`:
            hostname: hostname
            username: username
            password: $crypted_pass
        :ref:`ai-ssh`:
            install-server: yes
            authorized-keys:
              - $key
            allow-pw: no
        :ref:`ai-snaps`:
            - name: go
              channel: 1.20/stable
              classic: true
        :ref:`ai-debconf-selections`: |
            bind9      bind9/run-resolvconf    boolean false
        :ref:`ai-packages`:
            - libreoffice
            - dns-server^
        :ref:`ai-user-data`:
            disable_root: false
        :ref:`ai-late-commands`:
            - sed -ie 's/GRUB_TIMEOUT=.\*/GRUB_TIMEOUT=30/' /target/etc/default/grub
        :ref:`ai-error-commands`:
            - tar c /var/log/installer | nc 192.168.0.1 1000


Error handling
==============

Progress through the installer is reported via the :ref:`ai-reporting` system,
including errors. In addition, when a fatal error occurs, the
:ref:`ai-error-commands` are executed and the traceback printed to the console.
The server then just waits.
