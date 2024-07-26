.. _ai:

Autoinstall configuration reference manual
==========================================

The autoinstall file uses the YAML format. At the top level is a single key, ``autoinstall``, which contains a mapping of the keys described in this document. Unrecognised keys are ignored in version 1, but they will cause a fatal validation error in future versions.

Here is an example of a minimal autoinstall configuration:

.. code-block:: yaml

    autoinstall:
      version: 1
      identity:
       ...


At the top level is the ``autoinstall`` keyword. It contains a ``version`` section and an (incomplete) ``identity`` section, which are explained in more detail below. Any other key at the level of ``autoinstall`` results in an autoinstall validation error at run time.

.. note::

    This behaviour was first introduced during 24.04 (Noble). On any ISOs built before 24.04, you need to refresh the installer to see this behaviour.

    Technically, in all but one case the top level ``autoinstall`` keyword is strictly unnecessary. This keyword is only necessary when serving autoinstall via cloud-config. For backwards compatibility, this format is still supported for delivery methods not based on cloud-config; however, it is **highly recommended** to use the format with a top-level ``autoinstall`` keyword because mistakes in this formatting are a common source of confusion.


.. _ai-schema:

Schema
------

Autoinstall configurations are :doc:`validated against a JSON schema <autoinstall-schema>` before they are
used.

.. _ai-command-lists:

Command lists
-------------

Several configuration keys are lists of commands to be executed. Each command can be a string (in which case it is executed via :command:`sh -c`) or a list, in which case it is executed directly. Any command exiting with a non-zero return code is considered an error and aborts the installation (except for error-commands, where it is ignored).

.. _ai-top-level-keys:

Top-level keys
--------------

The following keys can be used to configure various aspects of the installation. If the global ``autoinstall`` key is provided, then all "top-level keys" must be provided underneath it and "top-level" refers to this sub-level. The examples below demonstrate this structure.

.. warning::

  In version 1, Subiquity emits warnings when encountering unrecognised keys. In later versions, it results in a fatal validation error, and the installation halts.

.. _ai-version:

version
~~~~~~~

* **type:** integer
* **default:** no default

A future-proofing configuration file version field. Currently, this must be ``1``.

.. _ai-interactive-sections:

interactive-sections
~~~~~~~~~~~~~~~~~~~~

* **type:** list of strings
* **default:** []

A list of configuration keys to still show in the user interface (UI). For example:

.. code-block:: yaml

    autoinstall:
      version: 1
      interactive-sections:
        - network
      identity:
        username: ubuntu
        password: $crypted_pass

This example stops on the network screen and allows the user to change the defaults. If a value is provided for an interactive section, it is used as the default.

You can use the special section name of ``*`` to indicate that the installer should ask all the usual questions -- in this case, the :file:`autoinstall.yaml` file is an autoinstall file. It just provides a way to change the defaults in the UI.

Not all configuration keys correspond to screens in the UI. This documentation indicates if a given section can be interactive or not.

If there are any interactive sections at all, the :ref:`ai-reporting` key is ignored.

.. _ai-early-commands:

early-commands
~~~~~~~~~~~~~~

* **type:** :ref:`command list<ai-command-lists>`
* **default:** no commands
* **can be interactive:** no

A list of shell commands to invoke as soon as the installer starts, in particular before probing for block and network devices. The autoinstall configuration is available at :file:`/autoinstall.yaml` (irrespective of how it was provided), and the file is re-read after the ``early-commands`` have run to allow them to alter the configuration if necessary.

.. _ai-locale:

locale
~~~~~~

* **type:** string
* **default:** ``en_US.UTF-8``
* **can be interactive:** true

The locale to configure for the installed system.

.. _ai-refresh-installer:

refresh-installer
~~~~~~~~~~~~~~~~~

* **type:** mapping
* **default:** see below
* **can be interactive:** true

Controls whether the installer updates to a new version available in the given channel before continuing.

The mapping contains keys:

update
^^^^^^

* **type:** boolean
* **default:** ``false``

Whether to update or not.

channel
^^^^^^^

* **type:** string
* **default:** ``"stable/ubuntu-$REL"``

The channel to check for updates.

.. _ai-keyboard:

keyboard
~~~~~~~~

* **type:** mapping, see below
* **default:** US English keyboard
* **can be interactive:** true

The layout of any attached keyboard. The mapping keys correspond to settings in the :file:`/etc/default/keyboard` configuration file. See the :manualpage:`keyboard(5) manual page <man5/keyboard.5.html>` for more details.

The mapping contains keys:

layout
^^^^^^

* **type:** string
* **default:** ``"us"``

Corresponds to the ``XKBLAYOUT`` setting.

variant
^^^^^^^

* **type:** string
* **default:** ``""``

Corresponds to the ``XKBVARIANT`` setting.

toggle
^^^^^^

* **type:** string or null
* **default:** ``null``

Corresponds to the value of ``grp:`` option from the ``XKBOPTIONS`` setting. Acceptable values are (the installer does not validate these):

* ``caps_toggle``
* ``toggle``
* ``rctrl_toggle``
* ``rshift_toggle``
* ``rwin_toggle``
* ``menu_toggle``
* ``alt_shift_toggle``
* ``ctrl_shift_toggle``
* ``ctrl_alt_toggle``
* ``alt_caps_toggle``
* ``lctrl_lshift_toggle``
* ``lalt_toggle``
* ``lctrl_toggle``
* ``lshift_toggle``
* ``lwin_toggle``
* ``sclk_toggle``

.. warning:: The version of Subiquity released with 20.04 GA does not accept ``null`` for this field due to a bug.

.. _ai-source:

source
~~~~~~

* **type:** mapping, see below
* **default:** see below
* **can be interactive:** true

search_drivers
^^^^^^^^^^^^^^

* **type:** boolean
* **default:** ``true`` (mostly, see below)

Whether the installer searches for available third-party drivers. When set to ``false``, it disables the drivers :ref:`screen and section<ai-drivers>`.

The default is ``true`` for most installations, and ``false`` when a "core boot" or "enhanced secure boot" method is selected (where third-party drivers cannot be currently installed).

id
^^

* **type:** string
* **default:** identifier of the first available source.

Identifier of the source to install (e.g., ``ubuntu-server-minimal``).

.. _ai-network:

network
~~~~~~~

* **type:** Netplan-format mapping, see below
* **default:** DHCP on interfaces named ``eth*`` or ``en*``
* **can be interactive:** true

`Netplan-formatted <https://netplan.io/reference>`_ network configuration. This is applied during installation as well as in the installed system. The default is to interpret the configuration for the installation media, which runs DHCP version 4 on any interface with a name matching ``eth*`` or ``en*`` but then disables any interface that does not receive an address.

For example, to run DHCP version 6 on a specific network interface:

.. code-block:: yaml

    autoinstall:
      network:
        version: 2
        ethernets:
          enp0s31f6:
            dhcp6: true

Note that in the 20.04 GA release of Subiquity, the behaviour is slightly different and requires you to write this with an extra ``network:`` key:

.. code-block:: yaml

    autoinstall:
      network:
        network:
          version: 2
          ethernets:
            enp0s31f6:
              dhcp6: true

Versions later than 20.04 support this syntax, too (for compatibility). When using a newer version, use the regular syntax.

.. _ai-proxy:

proxy
~~~~~

* **type:** URL or ``null``
* **default:** no proxy
* **can be interactive:** true

The proxy to configure both during installation and for ``apt`` and ``snapd`` in the target system. This setting is currently not honoured when running the geoip lookup.

Example:

.. code-block:: yaml

    autoinstall:
      proxy: http://172.16.90.1:3128

.. _ai-apt:

apt
~~~

* **type:** mapping
* **default:** see below
* **can be interactive:** true

APT configuration, used both during the installation and once booted into the target system.

This section historically used the same format as curtin, which is documented in the `APT Source <https://curtin.readthedocs.io/en/latest/topics/apt_source.html>`_ section of the curtin documentation. Nonetheless, some key differences with the format supported by curtin have been introduced:

- Subiquity supports an alternative format for the ``primary`` section, allowing configuration of a list of candidate primary mirrors. During installation, Subiquity automatically tests the specified mirrors and selects the first one that appears usable. This new behaviour is only activated when the ``primary`` section is wrapped in the ``mirror-selection`` section.

- The ``fallback`` key controls what Subiquity does when no primary mirror is usable.

- The ``geoip`` key controls whether to perform IP-based geolocation to determine the correct country mirror.

The default is:

.. code-block:: yaml

    autoinstall:
      apt:
        preserve_sources_list: false
        mirror-selection:
          primary:
            - country-mirror
            - arches: [i386, amd64]
              uri: "http://archive.ubuntu.com/ubuntu"
            - arches: [s390x, arm64, armhf, powerpc, ppc64el, riscv64]
              uri: "http://ports.ubuntu.com/ubuntu-ports"
        fallback: abort
        geoip: true

mirror-selection
^^^^^^^^^^^^^^^^

If the ``primary`` section is contained within the ``mirror-selection`` section, the automatic mirror selection is enabled. This is the default in new installations.

primary (when placed inside the ``mirror-selection`` section)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

* **type:** custom, see below

In the new format, the ``primary`` section expects a list of mirrors, which can be expressed in two different ways:

* The special ``country-mirror`` value
* A mapping with the following keys:

  * ``uri``: The URI of the mirror to use, e.g., ``http://fr.archive.ubuntu.com/ubuntu``.
  * ``arches``: An optional list of architectures supported by the mirror. By default, this list contains the current CPU architecture.

fallback
^^^^^^^^

* **type:** string (enumeration)
* **default:** offline-install

Controls what Subiquity does when no primary mirror is usable. Supported values are:

* ``abort``: abort the installation
* ``offline-install``: revert to an offline installation
* ``continue-anyway``: attempt to install the system anyway (not recommended; the installation fails)

geoip
^^^^^

* **type:** boolean
* **default:** ``true``

If ``geoip`` is set to ``true`` and one of the candidate primary mirrors has the special value ``country-mirror``, a request is made to ``https://geoip.ubuntu.com/lookup``. Subiquity then sets the mirror URI to ``http://CC.archive.ubuntu.com/ubuntu`` (or similar for ports) where ``CC`` is the country code returned by the lookup. If this section is not interactive, the request expires after 10 seconds.

If the legacy behaviour (i.e., without mirror-selection) is in use, the geolocation request is made if the mirror to be used is the default, and its URI is replaced by the proper country mirror URI.

To specify a mirror, use a configuration like this:

.. code-block:: yaml

    autoinstall:
      apt:
        mirror-selection:
          primary:
            - uri: YOUR_MIRROR_GOES_HERE
            - country-mirror
            - uri: http://archive.ubuntu.com/ubuntu

To add a PPA:

.. code-block:: yaml

    autoinstall:
      apt:
        sources:
          curtin-ppa:
            source: ppa:curtin-dev/test-archive

.. _ai-storage:

storage
~~~~~~~

* **type:** mapping, see below
* **default:** use the ``lvm`` layout on single-disk systems; there is no default for multiple-disk systems
* **can be interactive:** true

Storage configuration is a complex topic, and the description of the desired configuration in the autoinstall file can also be complex. The installer supports "layouts"; simple ways of expressing common configurations.

Supported layouts
^^^^^^^^^^^^^^^^^

The three supported layouts at the time of writing are ``lvm``, ``direct`` and ``zfs``.

.. code-block:: yaml

    autoinstall:
      storage:
        layout:
          name: lvm
      storage:
        layout:
          name: direct
      storage:
        layout:
          name: zfs


By default, these layouts install to the largest disk in a system, but you can supply a match spec (see below) to indicate which disk to use:

.. code-block:: yaml

    autoinstall:
      storage:
        layout:
          name: lvm
          match:
            serial: CT*
      storage:
        layout:
          name: direct
          match:
            ssd: true

.. note:: Match spec -- using ``match: {}`` matches an arbitrary disk.

When using the ``lvm`` layout, LUKS encryption can be enabled by supplying a password.

.. code-block:: yaml

    autoinstall:
      storage:
        layout:
          name: lvm
          password: LUKS_PASSPHRASE

The default is to use the ``lvm`` layout.

Sizing-policy
^^^^^^^^^^^^^

The ``lvm`` layout, by default, attempts to leave room for snapshots and further expansion. A sizing-policy key may be supplied to control this behaviour.

* **type:** string (enumeration)
* **default:** scaled

Supported values are:

* ``scaled``: Adjust space allocated to the root logical volume (LV) based on space available to the volume group (VG).
* ``all``: Allocate all remaining VG space to the root LV.

The scaling system uses the following rules:

* Less than 10 GiB: use all remaining space for the root file system
* Between 10--20 GiB: 10 GiB root file system
* Between 20--200 GiB: use half of the remaining space for the root file system
* Greater than 200 GiB: 100 GiB root file system

Example with no size scaling and a passphrase:

.. code-block:: yaml

    autoinstall:
      storage:
        layout:
          name: lvm
          sizing-policy: all
          password: LUKS_PASSPHRASE

Reset Partition
^^^^^^^^^^^^^^^

``reset-partition`` is used for creating a Reset Partition, which is a FAT32 file system containing the entire content of the installer image, so that the user can start the installer from GRUB or EFI without using the installation media. This option is useful for OEM system provisioning.

By default, the size of a Reset Partition is roughly 1.1x the used file system size of the installation media.

An example to enable Reset Partition:

.. code-block:: yaml

    autoinstall:
      storage:
        layout:
          name: direct
          reset-partition: true

The size of the reset partition can also be fixed to a specified size.  This is an example to fix Reset Partition to 12 GiB:

.. code-block:: yaml

    autoinstall:
      storage:
        layout:
          name: direct
          reset-partition: 12G

The installer can also install Reset Partition without installing the system.  To do this, set ``reset-partition-only`` to ``true``:

.. code-block:: yaml

    autoinstall:
      storage:
        layout:
          name: direct
          reset-partition: true
          reset-partition-only: true

Action-based configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^

For full flexibility, the installer allows storage configuration to be done using a syntax that is a superset of that supported by curtin, as described in the `Storage <https://curtin.readthedocs.io/en/latest/topics/storage.html>`_ section of the curtin documentation.

If the ``layout`` feature is used to configure the disks, the ``config`` section is not used.

The list of actions can be added under the ``config`` key, and the `grub <https://curtin.readthedocs.io/en/latest/topics/config.html#grub>`_ and `swap <https://curtin.readthedocs.io/en/latest/topics/config.html#swap>`_
curtin configuration items can also be included here.

An example storage section:

.. code-block:: yaml

    autoinstall:
      storage:
        swap:
          size: 0
        config:
          - type: disk
            id: disk0
            serial: ADATA_SX8200PNP_XXXXXXXXXXX
          - type: partition
            ...

The extensions to the curtin syntax allow for disk selection and partition or logical-volume sizing.

Disk selection extensions
^^^^^^^^^^^^^^^^^^^^^^^^^

Curtin supported identifying disks by serial numbers (e.g. ``Crucial_CT512MX100SSD1_14250C57FECE``) or by path (e.g. ``/dev/sdc``), and the server installer supports this, too. The installer additionally supports a "match spec" on a disk action, which provides for more flexible matching.

The actions in the storage configuration are processed in the order they are in the autoinstall file. Any disk action is assigned a matching disk -- chosen arbitrarily from the set of unassigned disks if there is more than one, and causing the installation to fail if there is no unassigned matching disk.

A match spec supports the following keys:

* ``model: value``: matches a disk where ``ID_MODEL=value`` in udev, supporting globbing

* ``vendor: value``: matches a disk where ``ID_VENDOR=value`` in udev, supporting globbing

* ``path: value``: matches a disk based on path (e.g. ``/dev/sdc``), supporting globbing (the globbing support distinguishes this from specifying ``path: value`` directly in the disk action)

* ``id_path: value``: matches a disk where ``ID_PATH=value`` in udev, supporting globbing

* ``devpath: value``: matches a disk where ``DEVPATH=value`` in udev, supporting globbing

* ``serial: value``: matches a disk where ``ID_SERIAL=value`` in udev, supporting globbing (the globbing support distinguishes this from specifying ``serial: value`` directly in the disk action)

* ``ssd: true|false``: matches a disk that is or is not an SSD (as opposed to a rotating drive)

* ``size: largest|smallest``: take the largest or smallest disk rather than an arbitrary one if there are multiple matches (support for ``smallest`` added in version 20.06.1)

A special sort of key is ``install-media: true``, which takes the disk the installer was loaded from (the ``ssd`` and ``size`` selectors never return this disk). If installing to the installation media, be careful to not overwrite the installer itself.

For example, to match an arbitrary disk:

.. code-block:: yaml

   - type: disk
     id: disk0

To match the largest SSD:

.. code-block:: yaml

   - type: disk
     id: big-fast-disk
     match:
       ssd: true
       size: largest

To match a Seagate drive:

.. code-block:: yaml

   - type: disk
     id: data-disk
     match:
       model: Seagate

As of Subiquity 24.08.1, match specs may optionally be specified in an ordered
list, and will use the first match spec that matches one or more unused disks:

.. code-block:: yaml

   # attempt first to match by serial, then by path
   - type: disk
     id: data-disk
     match:
       - serial: Foodisk_1TB_ABC123_1
       - path: /dev/nvme0n1

Partition/logical volume extensions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The size of a partition or logical volume in curtin is specified as a number of bytes. The autoinstall configuration is more flexible:

* You can specify the size using the ``1G``, ``512M`` syntax supported in the installer UI.

* You can specify the size as a percentage of the containing disk (or RAID), e.g. ``50%``.

* For the last partition specified for a particular device, you can specify the size as ``-1`` to indicate that the partition should fill the remaining space.

.. code-block:: yaml

   - type: partition
     id: boot-partition
     device: root-disk
     size: 10%
   - type: partition
     id: root-partition
     size: 20G
   - type: partition
     id: data-partition
     device: root-disk
     size: -1

.. _ai-identity:

identity
~~~~~~~~

* **type:** mapping, see below
* **default:** no default
* **can be interactive:** true

Configure the initial user for the system. This is the only configuration key that must be present (unless the :ref:`user-data section <ai-user-data>` is present, in which case it is optional).

A mapping that can contain keys, all of which take string values:

realname
^^^^^^^^

The real name for the user. This field is optional.

username
^^^^^^^^

The user name to create.

hostname
^^^^^^^^

The hostname for the system.

password
^^^^^^^^

The password for the new user, encrypted. This is required for use with ``sudo``, even if SSH access is configured.

The encrypted password string must conform to what the ``passwd`` command requires. See the :manualpage:`passwd(1) manual page <man1/passwd.1.html>` for details. Quote the password hash to ensure correct treatment of any special characters.

Several tools can generate the encrypted password, such as ``mkpasswd`` from the ``whois`` package, or ``openssl passwd``.

Example:

.. code-block:: yaml

    autoinstall:
      identity:
        realname: 'Ubuntu User'
        username: ubuntu
        password: '$6$wdAcoXrU039hKYPd$508Qvbe7ObUnxoj15DRCkzC3qO7edjH0VV7BPNRDYK4QR8ofJaEEF2heacn0QgD.f8pO8SNp83XNdWG6tocBM1'
        hostname: ubuntu

.. _ai-active-directory:

active-directory
~~~~~~~~~~~~~~~~

* **type:** mapping, see below
* **default:** no default
* **can be interactive:** true

Accepts data required to join the target system in an Active Directory domain.

A mapping that can contain keys, all of which take string values:

admin-name
^^^^^^^^^^

A domain account name with the privilege to perform the join operation. The account password is requested during run time.

domain-name
^^^^^^^^^^^

The Active Directory domain to join.

.. _ai-ubuntu-pro:

ubuntu-pro
~~~~~~~~~~

* **type:** mapping, see below
* **default:** see below
* **can be interactive:** true

token
^^^^^

* **type:** string
* **default:** no token

A contract token to attach to an existing Ubuntu Pro subscription.

.. _ai-ssh:

ssh
~~~

* **type:** mapping, see below
* **default:** see below
* **can be interactive:** true

Configure SSH for the installed system. A mapping that can contain the following keys:

install-server
^^^^^^^^^^^^^^

* **type:** boolean
* **default:** ``false``

Whether to install the OpenSSH server in the target system.

authorized-keys
^^^^^^^^^^^^^^^

* **type:** list of strings
* **default:** ``[]``

A list of SSH public keys to install in the initial user account.

allow-pw
^^^^^^^^

* **type:** boolean
* **default:** ``true`` if ``authorized_keys`` is empty, ``false`` otherwise

.. _ai-codecs:

codecs
~~~~~~

* **type:** mapping, see below
* **default:** see below
* **can be interactive:** no

Configure whether common restricted packages (including codecs) from the multiverse repository are to be installed.

install
^^^^^^^

* **type:** boolean
* **default:** ``false``

Whether to install the ``ubuntu-restricted-addons`` package.

.. _ai-drivers:

drivers
~~~~~~~

* **type:** mapping, see below
* **default:** see below
* **can be interactive:** true

install
^^^^^^^

* **type:** boolean
* **default:** ``false``

Whether to install the available third-party drivers.

.. _ai-oem:

oem
~~~

* **type:** mapping, see below
* **default:** see below
* **can be interactive:** no

install
^^^^^^^

* **type:** boolean or string (special value ``auto``)
* **default:**: ``auto``

Whether to install the available OEM meta-packages. The special value ``auto`` -- which is the default -- enables the installation on Ubuntu Desktop but not on Ubuntu Server. This option has no effect on core boot classic.

.. _ai-snaps:

snaps
~~~~~

* **type:** list
* **default:** install no extra snaps
* **can be interactive:** true

A list of snaps to install. Each snap is represented as a mapping with a required ``name`` and an optional ``channel`` (default is ``stable``) and classic (default is ``false``) keys. For example:

.. code-block:: yaml

    autoinstall:
      snaps:
        - name: etcd
          channel: edge
          classic: false

.. _ai-debconf-selections:

debconf-selections
~~~~~~~~~~~~~~~~~~

* **type:** string
* **default:** no configuration
* **can be interactive:** no

The installer updates the target with debconf ``set-selection`` values. Users need to be familiar with the options of the ``debconf`` package.

.. _ai-packages:

packages
~~~~~~~~

* **type:** list
* **default:** no packages
* **can be interactive:** no

A list of packages to install into the target system. Specifically, a list of strings to pass to the :command:`apt-get install` command. Therefore, this includes things such as task selection (``dns-server^``) and installing particular versions of a package (``my-package=1-1``).

.. _ai-kernel:

kernel
~~~~~~

* **type:** mapping (mutually exclusive), see below
* **default:** default kernel
* **can be interactive:** no

Which kernel gets installed. Either the name of the package or the name of the flavour must be specified.

package
^^^^^^^

**type:** string

The name of the package, e.g., ``linux-image-5.13.0-40-generic``.

flavor
^^^^^^

* **type:** string

The ``flavor`` of the kernel, e.g., ``generic`` or ``hwe``.

.. _ai-timezone:

timezone
~~~~~~~~

* **type:** string
* **default:** no timezone
* **can be interactive:** no

The timezone to configure on the system. The special value ``geoip`` can be used to query the timezone automatically over the network.

.. _ai-updates:

updates
~~~~~~~

* **type:** string (enumeration)
* **default:** ``security``
* **can be interactive:** no

The type of updates that will be downloaded and installed after the system installation. Supported values are:

* ``security``: download and install updates from the ``-security`` pocket.
* ``all``: also download and install updates from the ``-updates`` pocket.

.. _ai-shutdown:

shutdown
~~~~~~~~

* **type:** string (enumeration)
* **default:** ``reboot``
* **can be interactive:** no

Request the system to power off or reboot automatically after the installation has finished. Supported values are:

* ``reboot``
* ``poweroff``

.. _ai-late-commands:

late-commands
~~~~~~~~~~~~~

* **type:** :ref:`command list<ai-command-lists>`
* **default:** no commands
* **can be interactive:** no

Shell commands to run after the installation has completed successfully and any updates and packages installed, just before the system reboots. The commands are run in the installer environment with the installed system mounted at ``/target``. You can run ``curtin in-target -- $shell_command`` (with the version of Subiquity
released with 20.04 GA, you need to specify this as ``curtin in-target --target=/target -- $shell_command``) to run in the target system (similar to how plain ``in-target`` can be used in ``d-i preseed/late_command``).

.. _ai-error-commands:

error-commands
~~~~~~~~~~~~~~

* **type:** :ref:`command list<ai-command-lists>`
* **default:** no commands
* **can be interactive:** no

Shell commands to run after the installation has failed. They are run in the installer environment, and the target system (or as much of it as the installer managed to configure) is mounted at ``/target``. Logs will be available in :file:`/var/log/installer` in the live session.

.. _ai-reporting:

reporting
~~~~~~~~~

* **type:** mapping
* **default:** ``type: print`` (which causes output on ``tty1`` and any configured serial consoles)
* **can be interactive:** no

The installer supports reporting progress to a variety of destinations. Note that this section is ignored if there are any :ref:`interactive sections <ai-interactive-sections>`; it only applies to fully automated installations.

The configuration is similar to that used by curtin. See the `Reporting <https://curtin.readthedocs.io/en/latest/topics/reporting.html>`_ section of the curtin documentation.

Each key in the ``reporting`` mapping in the configuration defines a destination where the ``type`` sub-key is one of:

* ``print``: print progress information on ``tty1`` and any configured serial console. There is no other configuration.
* ``rsyslog``: report progress via rsyslog. The ``destination`` key specifies where to send output. (The rsyslog reporter does not yet exist.)
* ``webhook``: report progress by sending JSON reports to a URL using POST requests. Accepts the same `configuration as curtin <https://curtin.readthedocs.io/en/latest/topics/reporting.html#webhook-reporter>`_.
* ``none``: do not report progress. Only useful to inhibit the default output.

Reporting examples:

The default configuration is:

.. code-block:: yaml

   autoinstall:
     reporting:
       builtin:
         type: print

Report to rsyslog:

.. code-block:: yaml

   autoinstall:
     reporting:
       central:
         type: rsyslog
         destination: "@192.168.0.1"


Suppress the default output:

.. code-block:: yaml

   autoinstall:
     reporting:
       builtin:
         type: none

Report to a curtin-style webhook:

.. code-block:: yaml

   autoinstall:
     reporting:
       hook:
         type: webhook
         endpoint: http://example.com/endpoint/path
         consumer_key: "ck_value"
         consumer_secret: "cs_value"
         token_key: "tk_value"
         token_secret: "tk_secret"
         level: INFO

.. _ai-user-data:

user-data
~~~~~~~~~

* **type:** mapping
* **default:** ``{}``
* **can be interactive:** no

Provide cloud-init user data, which will be merged with the user data the installer produces. If you supply this, you don't need to supply an :ref:`identity section <ai-identity>` (in that case, ensure you can log in to the installed system).
