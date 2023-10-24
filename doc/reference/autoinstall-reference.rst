.. _ai:

Autoinstall configuration reference manual
******************************************

The autoinstall file is YAML. At top level it must be a mapping containing the
keys described in this document. Unrecognised keys are ignored.

.. _ai-schema:

Schema
======

Autoinstall configurations are
:doc:`validated against a JSON schema<autoinstall-schema>` before they are
used.

.. _ai-command-lists:

Command lists
=============

Several configuration keys are lists of commands to be executed. Each command can be
a string (in which case it is executed via ``sh -c``) or a list, in which case
it is executed directly. Any command exiting with a non-zero return code is
considered an error and aborts the installation (except for error-commands, where
it is ignored).

.. _ai-top-level-keys:

Top-level keys
==============

.. _ai-version:

version
-------

* **type:** integer
* **default:** no default

A future-proofing configuration file version field. Currently this must be "1".

.. _ai-interactive-sections:

interactive-sections
--------------------

* **type:** list of strings
* **default:** []

A list of configuration keys to still show in the UI. For example:

.. code-block:: yaml

    version: 1
    interactive-sections:
      - network
    identity:
      username: ubuntu
      password: $crypted_pass

This example stops on the network screen and allows the user to change the defaults. If
a value is provided for an interactive section, it is used as the default.

You can use the special section name of ``*`` to indicate that the installer
should ask all the usual questions -- in this case, the :file:`autoinstall.yaml`
file is not really an "autoinstall" file at all, instead just a way to change
the defaults in the UI.

Not all configuration keys correspond to screens in the UI. This documentation
indicates if a given section can be interactive or not.

If there are any interactive sections at all, the :ref:`ai-reporting` key is
ignored.

.. _ai-early-commands:

early-commands
--------------

* **type:** :ref:`command list<ai-command-lists>`
* **default:** no commands
* **can be interactive:** no

A list of shell commands to invoke as soon as the installer starts, in
particular before probing for block and network devices. The autoinstall
configuration is available at :file:`/autoinstall.yaml` (irrespective of how it was
provided) and the file will be re-read after the ``early-commands`` have run to
allow them to alter the configuration if necessary.

.. _ai-locale:

locale
------

* **type:** string
* **default:** ``en_US.UTF-8``
* **can be interactive:** yes

The locale to configure for the installed system.

.. _ai-refresh-installer:

refresh-installer
-----------------

* **type:** mapping
* **default:** see below
* **can be interactive:** yes

Controls whether the installer updates to a new version available in the given
channel before continuing.

The mapping contains keys:

update
~~~~~~

* **type:** boolean
* **default:** ``false``

Whether to update or not.

channel
~~~~~~~

* **type:** string
* **default:** ``"stable/ubuntu-$REL"``

The channel to check for updates.

.. _ai-keyboard:

keyboard
--------

* **type:** mapping, see below
* **default:** US English keyboard
* **can be interactive:** yes

The layout of any attached keyboard. Often systems being automatically
installed will not have a keyboard at all in which case the value used here
does not matter.

The mapping keys correspond to settings in the :file:`/etc/default/keyboard`
configuration file. See the :manualpage:`keyboard(5) manual page <man5/keyboard.5.html>`
for more details.

The mapping contains keys:

layout
~~~~~~

* **type:** string
* **default:** ``"us"``

Corresponds to the ``XKBLAYOUT`` setting.

variant
~~~~~~~

* **type:** string
* **default:** ``""``

Corresponds to the ``XKBVARIANT`` setting.

toggle
~~~~~~

* **type:** string or null
* **default:** ``null``

Corresponds to the value of ``grp:`` option from the ``XKBOPTIONS`` setting.
Acceptable values are (but note that the installer does not validate these):
``caps_toggle``, ``toggle``, ``rctrl_toggle``, ``rshift_toggle``,
``rwin_toggle``, ``menu_toggle``, ``alt_shift_toggle``, ``ctrl_shift_toggle``,
``ctrl_alt_toggle``, ``alt_caps_toggle``, ``lctrl_lshift_toggle``,
``lalt_toggle``, ``lctrl_toggle``, ``lshift_toggle``, ``lwin_toggle``,
``sclk_toggle``

The version of Subiquity released with 20.04 GA does not accept ``null`` for
this field due to a bug.

.. _ai-source:

source
------

* **type:** mapping, see below
* **default:** see below
* **can be interactive:** yes

search_drivers
~~~~~~~~~~~~~~

* **type:** boolean
* **default:** ``true``

Whether the installer should search for available third-party drivers. When
set to ``false``, it disables the drivers :ref:`screen and section<ai-drivers>`.

id
~~

* **type:** string
* **default:** identifier of the first available source.

Identifier of the source to install (e.g., ``ubuntu-server-minimal``).

.. _ai-network:

network
-------

* **type:** Netplan-format mapping, see below
* **default:** DHCP on interfaces named ``eth*`` or ``en*``
* **can be interactive:** yes

`Netplan-formatted <https://netplan.io/reference>`_ network configuration.
This will be applied during installation as well as in the installed system.
The default is to interpret the configuration for the installation media, which runs
DHCP version 4 on any interface with a name matching ``eth*`` or ``en*`` but then
disables any interface that does not receive an address.

For example, to run DHCP version 6 on a specific network interface:

.. code-block:: yaml

    network:
      version: 2
      ethernets:
        enp0s31f6:
          dhcp6: true

Note that in the 20.04 GA release of Subiquity, the behaviour is slightly
different and requires you to write this with an extra ``network:`` key:

.. code-block:: yaml

    network:
      network:
        version: 2
        ethernets:
          enp0s31f6:
            dhcp6: true

Later versions support this syntax too (for compatibility) but if you can
assume a newer version you should use the former.

.. _ai-proxy:

proxy
-----

* **type:** URL or ``null``
* **default:** no proxy
* **can be interactive:** yes

The proxy to configure both during installation and for ``apt`` and for
``snapd`` in the target system.

.. _ai-apt:

apt
---

* **type:** mapping
* **default:** see below
* **can be interactive:** yes

APT configuration, used both during the installation and once booted into the target
system.

This section historically used the same format as curtin,
`which is documented here <https://curtin.readthedocs.io/en/latest/topics/apt_source.html>`_.
Nonetheless, some key differences with the format supported by curtin have been introduced:

- Subiquity supports an alternative format for the ``primary`` section,
  allowing configuration of a list of candidate primary mirrors. During
  installation, Subiquity will automatically test the specified mirrors and
  select the first one that seems usable. This new behaviour is only activated
  when the ``primary`` section is wrapped in the ``mirror-selection`` section.

- The ``fallback`` key controls what Subiquity should do if no primary mirror
  is usable.

- The ``geoip`` key controls whether a geoip lookup is done to determine the
  correct country mirror.

The default is:

.. code-block:: yaml

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
~~~~~~~~~~~~~~~~

if the ``primary`` section is contained within the ``mirror-selection``
section, the automatic mirror selection is enabled. This is the default in new installations.

primary (when placed inside the ``mirror-selection`` section):
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* **type:** custom, see below

In the new format, the ``primary`` section expects a list of mirrors, which
can be expressed in two different ways:

* The special value ``country-mirror``
* A mapping with the following keys:

  * ``uri``: The URI of the mirror to use, e.g., ``http://fr.archive.ubuntu.com/ubuntu``
  * ``arches``: An optional list of architectures supported by the mirror. By
    default, this list contains the current CPU architecture.

fallback
~~~~~~~~

* **type:** string (enumeration)
* **default:** abort

Controls what Subiquity should do if no primary mirror is usable. Supported
values are:

* ``abort`` -> abort the installation
* ``offline-install`` -> revert to an offline installation
* ``continue-anyway`` -> attempt to install the system anyway (not recommended,
  the installation will certainly fail)

geoip
~~~~~

* **type:** boolean
* **default:** ``true``

If geoip is true and one of the candidate primary mirrors has the special
value ``country-mirror``, a request is made to ``https://geoip.ubuntu.com/lookup``.
Subiquity then sets the mirror URI to ``http://CC.archive.ubuntu.com/ubuntu``
(or similar for ports) where ``CC`` is the country code returned by the lookup.
If this section is not interactive, the request is timed out after 10 seconds.

If the legacy behaviour (i.e., without mirror-selection) is in use, the geoip
request is made if the mirror to be used is the default, and its URI ends up
getting replaced by the proper country mirror URI.

If you just want to specify a mirror, you can use a configuration like this:

.. code-block:: yaml

    apt:
      mirror-selection:
        primary:
          - uri: YOUR_MIRROR_GOES_HERE
          - country-mirror
          - uri: http://archive.ubuntu.com/ubuntu

To add a PPA:

.. code-block:: yaml

    apt:
      sources:
        curtin-ppa:
          source: ppa:curtin-dev/test-archive

.. _ai-storage:

storage
-------

* **type:** mapping, see below
* **default:** use the ``lvm`` layout on single-disk systems; there is no default for
  multiple-disk systems
* **can be interactive:** yes

Storage configuration is a complex topic and the description of the desired
configuration in the autoinstall file can also be complex. The installer
supports "layouts"; simple ways of expressing common configurations.

Supported layouts
~~~~~~~~~~~~~~~~~

The three supported layouts at the time of writing are ``lvm``, ``direct`` and ``zfs``.

.. code-block:: yaml

    storage:
      layout:
        name: lvm
    storage:
      layout:
        name: direct
    storage:
      layout:
        name: zfs


By default these will install to the largest disk in a system, but you can
supply a match spec (see below) to indicate which disk to use:

.. code-block:: yaml

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

.. note::
   Match spec -- using "``match: {}``" will match an arbitrary disk

When using the ``lvm`` layout, LUKS encryption can be enabled by supplying a
password.

.. code-block:: yaml

    storage:
      layout:
        name: lvm
        password: LUKS_PASSPHRASE


The default is to use the ``lvm`` layout.

Sizing-policy
~~~~~~~~~~~~~

The ``lvm`` layout, by default, attempts to leave room for snapshots and
further expansion. A sizing-policy key may be supplied to control this
behaviour.

* **type:** string (enumeration)
* **default:** scaled

Supported values are:

* ``scaled`` -> adjust space allocated to the root LV based on space available
  to the VG
* ``all`` -> allocate all remaining VG space to the root LV

The scaling system is currently as follows:

* Less than 10 GiB: use all remaining space for root file system
* Between 10--20 GiB: 10 GiB root file system
* Between 20--200 GiB: use half of remaining space for root file system
* Greater than 200 GiB: 100 GiB root file system

Example with no size scaling and a passphrase:

.. code-block:: yaml

    storage:
      layout:
        name: lvm
        sizing-policy: all
        password: LUKS_PASSPHRASE

Action-based configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~

For full flexibility, the installer allows storage configuration to be done
using a syntax which is a superset of that supported by curtin, as described in
`the curtin documentation <https://curtin.readthedocs.io/en/latest/topics/storage.html>`_.

If the ``layout`` feature is used to configure the disks, the ``config`` section
is not used.

As well as putting the list of actions under the ``config`` key, the
`grub <https://curtin.readthedocs.io/en/latest/topics/config.html#grub>`_ and
`swap <https://curtin.readthedocs.io/en/latest/topics/config.html#swap>`_
curtin configuration items can be put here. So a storage section might look like:

.. code-block:: yaml

    storage:
      swap:
        size: 0
      config:
        - type: disk
          id: disk0
          serial: ADATA_SX8200PNP_XXXXXXXXXXX
        - type: partition
          ...


The extensions to the curtin syntax are around disk selection and
partition/logical volume sizing.

Disk selection extensions
~~~~~~~~~~~~~~~~~~~~~~~~~

Curtin supported identifying disks by serial (e.g.
``Crucial_CT512MX100SSD1_14250C57FECE``) or by path (e.g. ``/dev/sdc``) and the
server installer supports this as well. The installer additionally supports a
''match spec'' on a disk action that supports more flexible matching.

The actions in the storage configuration are processed in the order they are in the
autoinstall file. Any disk action is assigned a matching disk -- chosen
arbitrarily from the set of unassigned disks if there is more than one, and
causing the installation to fail if there is no unassigned matching disk.

A match spec supports the following keys:

* ``model: foo``: matches a disk where ``ID_VENDOR=foo`` in udev, supporting
  globbing
* ``path: foo``: matches a disk based on path (e.g. ``/dev/sdc``), supporting
  globbing (the globbing support distinguishes this from specifying path: foo
  directly in the disk action)
* ``id_path: foo``: matches a disk where ``ID_PATH=foo`` in udev, supporting
  globbing
* ``devpath: foo``: matches a disk where ``DEVPATH=foo`` in udev, supporting
  globbing
* ``serial: foo``: matches a disk where ``ID_SERIAL=foo`` in udev, supporting
  globbing (the globbing support distinguishes this from specifying serial: foo
  directly in the disk action)
* ``ssd: true|false``: matches a disk that is or is not an SSD (vs. a rotating
  drive)
* ``size: largest|smallest``: take the largest or smallest disk rather than an
  arbitrary one if there are multiple matches (support for ``smallest`` added
  in version 20.06.1)

A special sort of key is ``install-media: true``, which will take the disk the
installer was loaded from (the ``ssd`` and ``size`` selectors will never return
this disk). If installing to the installation media, care obviously needs to be taken
to not overwrite the installer itself!

So for example, to match an arbitrary disk it is simply:

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


Partition/logical volume extensions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The size of a partition or logical volume in curtin is specified as a number of
bytes. The autoinstall configuration is more flexible:

* You can specify the size using the "1G", "512M" syntax supported in the
  installer UI.
* You can specify the size as a percentage of the containing disk (or RAID),
  e.g. "50%".
* For the last partition specified for a particular device, you can specify
  the size as "-1" to indicate that the partition should fill the remaining
  space.

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
--------

* **type:** mapping, see below
* **default:** no default
* **can be interactive:** yes

Configure the initial user for the system. This is the only configuration key that
must be present (unless the :ref:`user-data section <ai-user-data>` is present,
in which case it is optional).

A mapping that can contain keys, all of which take string values:

realname
~~~~~~~~

The real name for the user. This field is optional.

username
~~~~~~~~

The user name to create.

hostname
~~~~~~~~

The hostname for the system.

password
~~~~~~~~

The password for the new user, encrypted. This is required for use with
``sudo``, even if SSH access is configured.

The encrypted password string must conform to what the
``passwd`` command requires. See the :manualpage:`passwd(1) manual page <man1/passwd.1.html>`
for details. Quote the password hash to ensure correct treatment of any special characters.

Several tools can generate the encrypted password, such as ``mkpasswd`` from the
``whois`` package, or ``openssl passwd``.

Example:

.. code-block:: yaml

    identity:
      realname: 'Ubuntu User'
      username: ubuntu
      password: '$6$wdAcoXrU039hKYPd$508Qvbe7ObUnxoj15DRCkzC3qO7edjH0VV7BPNRDYK4QR8ofJaEEF2heacn0QgD.f8pO8SNp83XNdWG6tocBM1'
      hostname: ubuntu

.. _ai-active-directory:

active-directory
----------------

* **type:** mapping, see below
* **default:** no default
* **can be interactive:** yes

Accepts data required to join the target system in an Active Directory domain.

A mapping that can contain keys, all of which take string values:

admin-name
~~~~~~~~~~

A domain account name with privilege to perform the join operation. That
account's password will be requested during run time.

domain-name
~~~~~~~~~~~

The Active Directory domain to join.

.. _ai-ubuntu-pro:

ubuntu-pro
----------

* **type:** mapping, see below
* **default:** see below
* **can be interactive:** yes

token
~~~~~

* **type:** string
* **default:** no token

A contract token to attach to an existing Ubuntu Pro subscription.

.. _ai-ssh:

ssh
---

* **type:** mapping, see below
* **default:** see below
* **can be interactive:** yes

Configure SSH for the installed system. A mapping that can contain keys:

install-server
~~~~~~~~~~~~~~

* **type:** boolean
* **default:** ``false``

Whether to install OpenSSH server in the target system.

:spellexception:`authorized-keys`
~~~~~~~~~~~~~~~

* **type:** list of strings
* **default:** ``[]``

A list of SSH public keys to install in the initial user's account.

allow-pw
~~~~~~~~

* **type:** boolean
* **default:** ``true`` if ``authorized_keys`` is empty, ``false`` otherwise

.. _ai-codecs:

codecs
------

* **type:** mapping, see below
* **default:** see below
* **can be interactive:** no

Configure whether common restricted packages (including codecs) from
[multiverse] should be installed.

install
~~~~~~~

* **type:** boolean
* **default:** ``false``

Whether to install the ubuntu-restricted-addons package.

.. _ai-drivers:

drivers
-------

* **type:** mapping, see below
* **default:** see below
* **can be interactive:** yes

install
~~~~~~~

* **type:** boolean
* **default:** ``false``

Whether to install the available third-party drivers.

.. _ai-oem:

oem
---

* **type:** mapping, see below
* **default:** see below
* **can be interactive:** no

install
~~~~~~~

* **type:** boolean or string (special value ``auto``)
* **default:**: ``auto``

Whether to install the available OEM meta-packages. The special value ``auto``
-- which is the default -- enables the installation on ubuntu-desktop but not
on ubuntu-server. This option has no effect on core boot classic.

.. _ai-snaps:

snaps
-----

* **type:** list
* **default:** install no extra snaps
* **can be interactive:** yes

A list of snaps to install. Each snap is represented as a mapping with required
``name`` and optional ``channel`` (defaulting to ``stable``) and classic
(defaulting to ``false``) keys. For example:

.. code-block: yaml

    snaps:
      - name: etcd
        channel: edge
        classic: false

.. _ai-debconf-selections:

debconf-selections
------------------

* **type:** string
* **default:** no configuration
* **can be interactive:** no

The installer will update the target with debconf set-selection values. Users
will need to be familiar with the package debconf options.

.. _ai-packages:

packages
--------

* **type:** list
* **default:** no packages
* **can be interactive:** no

A list of packages to install into the target system. More precisely, a list of
strings to pass to "``apt-get install``", so this includes things like task
selection (``dns-server^``) and installing particular versions of a package
(``my-package=1-1``).

.. _ai-kernel:

kernel
------

* **type:** mapping (mutually exclusive), see below
* **default:** default kernel
* **can be interactive:** no

Which kernel gets installed. Either the name of the package or the name of the
flavour must be specified.

package
~~~~~~~

**type:** string

The name of the package, e.g., ``linux-image-5.13.0-40-generic``

flavor
~~~~~~

* **type:** string

The ``flavor`` of the kernel, e.g., ``generic`` or ``hwe``.

.. _ai-timezone:

timezone
--------

* **type:** string
* **default:** no timezone
* **can be interactive:** no

The timezone to configure on the system. The special value "geoip" can be used
to query the timezone automatically over the network.

.. _ai-updates:

updates
-------

* **type:** string (enumeration)
* **default:** ``security``
* **can be interactive:** no

The type of updates that will be downloaded and installed after the system
installation. Supported values are:

* ``security`` -> download and install updates from the -security pocket
* ``all`` -> also download and install updates from the -updates pocket

.. _ai-shutdown:

shutdown
--------

* **type:** string (enumeration)
* **default:** ``reboot``
* **can be interactive:** no

Request the system to power off or reboot automatically after the installation
has finished. Supported values are:

* ``reboot``
* ``poweroff``

.. _ai-late-commands:

late-commands
-------------

* **type:** :ref:`command list<ai-command-lists>`
* **default:** no commands
* **can be interactive:** no

Shell commands to run after the installation has completed successfully and any
updates and packages installed, just before the system reboots. They are run in
the installer environment with the installed system mounted at ``/target``. You
can run ``curtin in-target -- $shell_command`` (with the version of Subiquity
released with 20.04 GA you need to specify this as
``curtin in-target --target=/target -- $shell_command``) to run in the target
system (similar to how plain ``in-target`` can be used in
``d-i preseed/late_command``).

.. _ai-error-commands:

error-commands
--------------

* **type:** :ref:`command list<ai-command-lists>`
* **default:** no commands
* **can be interactive:** no

Shell commands to run after the installation has failed. They are run in the
installer environment, and the target system (or as much of it as the installer
managed to configure) will be mounted at ``/target``. Logs will be available
at :file:`/var/log/installer` in the live session.

.. _ai-reporting:

reporting
---------

* **type:** mapping
* **default:** ``type: print`` which causes output on tty1 and any configured
  serial consoles
* **can be interactive:** no

The installer supports reporting progress to a variety of destinations. Note
that this section is ignored if there are any :ref:`interactive sections <ai-interactive-sections>`; it only applies to fully automated installs.

The configuration, and indeed the implementation, is 90% the same as
`that used by curtin <https://curtin.readthedocs.io/en/latest/topics/reporting.html>`_.

Each key in the ``reporting`` mapping in the configuration defines a destination,
where the ``type`` sub-key is one of:

**The rsyslog reporter does not yet exist**

* **print**: print progress information on tty1 and any configured serial
  console. There is no other configuration.
* **rsyslog**: report progress via rsyslog. The **destination** key specifies
  where to send output.
* **webhook**: report progress by sending JSON reports to a URL using POST requests. Accepts the
  same `configuration as curtin <https://curtin.readthedocs.io/en/latest/topics/reporting.html#webhook-reporter>`_.
* **none**: do not report progress. Only useful to inhibit the default output.

Examples:

The default configuration is:

.. code-block:: yaml

   reporting:
     builtin:
       type: print

Report to rsyslog:

.. code-block:: yaml

   reporting:
     central:
       type: rsyslog
       destination: "@192.168.0.1"


Suppress the default output:

.. code-block:: yaml

   reporting:
     builtin:
       type: none

Report to a curtin-style webhook:

.. code-block:: yaml

   reporting:
     hook:
       type: webhook
       endpoint: http://example.com/endpoint/path
       consumer_key: "ck_foo"
       consumer_secret: "cs_foo"
       token_key: "tk_foo"
       token_secret: "tk_secret"
       level: INFO


.. _ai-user-data:

user-data
---------

* **type:** mapping
* **default:** ``{}``
* **can be interactive:** no

Provide cloud-init user data which will be merged with the user data the
installer produces. If you supply this, you don't need to supply an
:ref:`identity section <ai-identity>` (but then it's your responsibility to
make sure that you can log into the installed system!).
