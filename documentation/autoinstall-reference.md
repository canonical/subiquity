# Automated Server Installs Config File Reference

## Overall format

The autoinstall file is YAML. At top level it must be a mapping containing the keys described in this document. Unrecognized keys are ignored.

## Schema

Autoinstall configs [are validated against a JSON schema](autoinstall-schema.md) before they are used.

<a name="commandlist"></a>

## Command lists

Several config keys are lists of commands to be executed. Each command can be a string (in which case it is executed via "sh -c") or a list, in which case it is executed directly. Any command exiting with a non-zero return code is considered an error and aborts the install (except for error-commands, where it is ignored).

## Top-level keys

<a name="version"></a>

### version

**type:** integer
**default:** no default

A future-proofing config file version field. Currently this must be "1".

<a name="interactive-sections"></a>

### interactive-sections

**type:** list of strings
**default:** []

A list of config keys to still show in the UI. So for example:

    version: 1
    interactive-sections:
     - network
    identity:
     username: ubuntu
     password: $crypted_pass

Would stop on the network screen and allow the user to change the defaults. If a value is provided for an interactive section it is used as the default.

You can use the special section name of "\*" to indicate that the installer should ask all the usual questions -- in this case, the `autoinstall.yaml` file is not really an "autoinstall" file at all, instead just a way to change the defaults in the UI.

Not all config keys correspond to screens in the UI. This documentation indicates if a given section can be interactive or not.

If there are any interactive sections at all, the [reporting](#reporting) key is ignored.

<a name="early-commands"></a>

### early-commands

**type:** [command list](#commandlist)
**default:** no commands
**can be interactive:** no

A list of shell commands to invoke as soon as the installer starts, in particular before probing for block and network devices. The autoinstall config is available at `/autoinstall.yaml` (irrespective of how it was provided) and the file will be re-read after the `early-commands` have run to allow them to alter the config if necessary.

<a name="locale"></a>

### locale

**type:** string
**default:** `en_US.UTF-8`
**can be interactive:** yes, always interactive if any section is

The locale to configure for the installed system.

<a name="refresh-installer"></a>

### refresh-installer

**type:** mapping
**default:** see below
**can be interactive:** yes

Controls whether the installer updates to a new version available in the given channel before continuing.

The mapping contains keys:

#### update

**type:** boolean
**default:** `no`

Whether to update or not.

#### channel

**type:** string
**default:** `"stable/ubuntu-$REL"`

The channel to check for updates.

<a name="keyboard"></a>

### keyboard

**type:** mapping, see below
**default:** US English keyboard
**can be interactive:** yes

The layout of any attached keyboard. Often systems being automatically installed will not have a keyboard at all in which case the value used here does not matter.

The mapping's keys correspond to settings in the `/etc/default/keyboard` configuration file. See [its manual page](http://manpages.ubuntu.com/manpages/bionic/en/man5/keyboard.5.html) for more details.

The mapping contains keys:

#### layout

**type:** string
**default:** `"us"`

Corresponds to the `XKBLAYOUT` setting.

#### variant

**type:** string
**default:** `""`

Corresponds to the `XKBVARIANT` setting.

#### toggle

**type:** string or null
**default:** `null`

Corresponds to the value of `grp:` option from the `XKBOPTIONS` setting. Acceptable values are (but note that the installer does not validate these): `caps_toggle`, `toggle`, `rctrl_toggle`, `rshift_toggle`, `rwin_toggle`, `menu_toggle`, `alt_shift_toggle`, `ctrl_shift_toggle`, `ctrl_alt_toggle`, `alt_caps_toggle`, `lctrl_lshift_toggle`, `lalt_toggle`, `lctrl_toggle`, `lshift_toggle`, `lwin_toggle`, `sclk_toggle`

The version of subiquity released with 20.04 GA does not accept `null` for this field due to a bug.

### source
**type:** mapping, see below
**default:** see below
**can be interactive:** yes

#### search_drivers
**type:** boolean
**default:** `true`

Whether the installer should search for available third-party drivers. When set to `false`, it disables the drivers screen and [section](#drivers).

#### id
**type:** string
**default:** identifier of the first available source.

Identifier of the source to install (e.g., `"ubuntu-server-minimized"`).

<a name="network"></a>

### network

**type:** netplan-format mapping, see below
**default:** DHCP on interfaces named eth\* or en\*
**can be interactive:** yes

[netplan](https://netplan.io/reference) formatted network configuration. This will be applied during installation as well as in the installed system. The default is to interpret the config for the install media, which runs DHCPv4 on any interface with a name matching "eth\*" or "en\*" but then disables any interface that does not receive an address.

For example, to run dhcp6 on a particular NIC:

    network:
      version: 2
      ethernets:
        enp0s31f6:
          dhcp6: yes

Note that thanks to a bug, the version of subiquity released with 20.04 GA forces you to write this with an extra "network:" key like so:

    network:
      network:
        version: 2
        ethernets:
          enp0s31f6:
            dhcp6: yes

Later versions support this syntax too for compatibility but if you can assume a newer version you should use the former.

<a name="proxy"></a>

### proxy

**type:** URL or `null`
**default:** no proxy
**can be interactive:** yes

The proxy to configure both during installation and for apt and for snapd in the target system.

<a name="apt"></a>

### apt

**type:** mapping
**default:** see below
**can be interactive:** yes

Apt configuration, used both during the install and once booted into the target system.

This section historically used the same format as curtin, [which is documented here](https://curtin.readthedocs.io/en/latest/topics/apt_source.html). Nonetheless, some key differences with the format supported by curtin have been introduced:

 * Subiquity supports an alternative format for the `primary` section, allowing to configure a list of candidate primary mirrors. During installation, subiquity will automatically test the specified mirrors and select the first one that seems usable. This new behavior is only activated when the `primary` section is wrapped in the `mirror-selection` section.
 * The `fallback` key controls what subiquity should do if no primary mirror is usable.
 * The `geoip` key controls whether a geoip lookup is done to determine the correct country mirror.

The default is:

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

#### mirror-selection
if the `primary` section is contained within the `mirror-selection` section, the automatic mirror selection is enabled. This is the default in new installations.

#### primary (when placed inside the `mirror-selection` section):
**type:** custom, see below

In the new format, the `primary` section expects a list of mirrors, which can be expressed in two different ways:

 * the special value `country-mirror`
 * a mapping with the following keys:
   * `uri`: the URI of the mirror to use, e.g., "http://fr.archive.ubuntu.com/ubuntu"
   * `arches`: an optional list of architectures supported by the mirror. By default, this list contains the current CPU architecture.

#### fallback
**type:** string (enumeration)
**default:** abort

Controls what subiquity should do if no primary mirror is usable.
Supported values are:

 * `abort` -> abort the installation
 * `offline-install` -> revert to an offline installation
 * `continue-anyway` -> attempt to install the system anyway (not recommended, the installation will certainly fail)

#### geoip
**type:** boolean
**default:**: `true`

If geoip is true and one of the candidate primary mirrors has the special value `country-mirror`, a request is made to `https://geoip.ubuntu.com/lookup`. Subiquity then sets the mirror uri to `http://CC.archive.ubuntu.com/ubuntu` (or similar for ports) where `CC` is the country code returned by the lookup. If this section is not interactive, the request is timed out after 10 seconds.

If the legacy behavior (i.e., without mirror-selection) is in use, the geoip request is made if the mirror to be used is the default, and its uri ends up getting replaced by the proper country mirror uri.

If you just want to specify a mirror, you can use a configuration like this:

    apt:
        mirror-selection:
            primary:
                - uri: YOUR_MIRROR_GOES_HERE
                - country-mirror
                - uri: http://archive.ubuntu.com/ubuntu

To add a ppa:

    apt:
        sources:
            curtin-ppa:
                source: ppa:curtin-dev/test-archive

<a name="storage"></a>

### storage

**type:** mapping, see below
**default:** use "lvm" layout in a single disk system, no default in a multiple disk system
**can be interactive:** yes

Storage configuration is a complex topic and the description of the desired configuration in the autoinstall file can necessarily also be complex. The installer supports "layouts", simple ways of expressing common configurations.

#### Supported layouts

The two supported layouts at the time of writing are "lvm" and "direct".

    storage:
      layout:
        name: lvm
    storage:
      layout:
        name: direct

By default these will install to the largest disk in a system, but you can supply a match spec (see below) to indicate which disk to use:

    storage:
      layout:
        name: lvm
        match:
          serial: CT*
    storage:
      layout:
        name: disk
        match:
          ssd: yes

(you can just say "`match: {}`" to match an arbitrary disk)

When using the "lvm" layout, LUKS encryption can be enabled by supplying a password.

    storage:
      layout:
        name: lvm
        password: LUKS_PASSPHRASE

The default is to use the lvm layout.

#### action-based config

For full flexibility, the installer allows storage configuration to be done using a syntax which is a superset of that supported by curtin, described at https://curtin.readthedocs.io/en/latest/topics/storage.html.

If the "layout" feature is used to configure the disks, the "config" section will not be used.

As well as putting the list of actions under the 'config' key, the [grub](https://curtin.readthedocs.io/en/latest/topics/config.html#grub) and [swap](https://curtin.readthedocs.io/en/latest/topics/config.html#swap) curtin config items can be put here. So a storage section might look like:

    storage:
        swap:
            size: 0
        config:
            - type: disk
              id: disk0
              serial: ADATA_SX8200PNP_XXXXXXXXXXX
            - type: partition
              ...

The extensions to the curtin syntax are around disk selection and partition/logical volume sizing.

##### Disk selection extensions

Curtin supported identifying disks by serial (e.g. `Crucial_CT512MX100SSD1_14250C57FECE`) or by path (e.g. `/dev/sdc`) and the server installer supports this as well. The installer additionally supports a ''match spec'' on a disk action that supports more flexible matching.

The actions in the storage config are processed in the order they are in the autoinstall file. Any disk action is assigned a matching disk -- chosen arbitrarily from the set of unassigned disks if there is more than one, and causing the installation to fail if there is no unassigned matching disk.

A match spec supports the following keys:

 * `model: foo`: matches a disk where ID_VENDOR=foo in udev, supporting globbing
 * `path: foo`: matches a disk where DEVPATH=foo in udev, supporting globbing (the globbing support distinguishes this from specifying path: foo directly in the disk action)
 * `serial: foo`: matches a disk where ID_SERIAL=foo in udev, supporting globbing (the globbing support distinguishes this from specifying serial: foo directly in the disk action)
 * `ssd: yes|no`: matches a disk that is or is not an SSD (vs a rotating drive)
 * `size: largest|smallest`: take the largest or smallest disk rather than an arbitrary one if there are multiple matches (support for `smallest` added in version 20.06.1)

So for example, to match an arbitrary disk it is simply:

     - type: disk
       id: disk0

To match the largest ssd:

<pre><code> - type: disk
   id: big-fast-disk
   match:
     ssd: yes
     size: largest</code></pre>

To match a Seagate drive:

<pre><code> - type: disk
   id: data-disk
   match:
     model: Seagate</code></pre>

##### partition/logical volume extensions

The size of a partition or logical volume in curtin is specified as a number of bytes. The autoinstall config is more flexible:

 * You can specify the size using the "1G", "512M" syntax supported in the installer UI
 * You can specify the size as a percentage of the containing disk (or RAID), e.g. "50%"
 * For the last partition specified for a particular device, you can specify the size as "-1" to indicate that the partition should fill the remaining space.

<pre><code> - type: partition
   id: boot-partition
   device: root-disk
   size: 10%
 - type: partition
   id: root-partition
   size: 20G
 - type: partition
   id: data-partition
   device: root-disk
   size: -1</code></pre>

<a name="identity"></a>

### identity

**type:** mapping, see below
**default:** no default
**can be interactive:** yes

Configure the initial user for the system. This is the only config key that must be present (unless the [user-data section](#user-data) is present, in which case it is optional).

A mapping that can contain keys, all of which take string values:

#### realname

The real name for the user. This field is optional.

#### username

The user name to create.

#### hostname

The hostname for the system.

#### password

The password for the new user, crypted. This is required for use with sudo, even if SSH access is configured.

The crypted password string must conform to what [passwd](https://manpages.ubuntu.com/manpages/jammy/en/man1/passwd.1.html) expects.  Depending on the special characters in the password hash, quoting may be required, so it's safest to just always include the quotes around the hash.

Several tools can generate the crypted password, such as `mkpasswd` from the `whois` package, or `openssl passwd`.

Example:

```yaml
identity:
  realname: 'Ubuntu User'
  username: ubuntu
  password: '$6$wdAcoXrU039hKYPd$508Qvbe7ObUnxoj15DRCkzC3qO7edjH0VV7BPNRDYK4QR8ofJaEEF2heacn0QgD.f8pO8SNp83XNdWG6tocBM1'
  hostname: ubuntu
```

### active-directory

**type:** mapping, see below
**default:** no default
**can be interactive:** yes

Accepts data required to join the target system in an Active Directory domain.

A mapping that can contain keys, all of which take string values:

#### admin-name

A domain account name with privilege to perform the join operation. That account's password will be requested during runtime.

#### domain-name

The Active Directory domain to join.

### ubuntu-pro

**type:** mapping, see below
**default:** see below
**can be interactive:** yes

#### token

**type:** string
**default:** no token

A contract token to attach to an existing Ubuntu Pro subscription.

<a name="ssh"></a>

### ssh

**type:** mapping, see below
**default:** see below
**can be interactive:** yes

Configure ssh for the installed system. A mapping that can contain keys:

#### install-server

**type:** boolean
**default:** `false`

Whether to install OpenSSH server in the target system.

#### authorized-keys

**type:** list of strings
**default:** `[]`

A list of SSH public keys to install in the initial user's account.

#### allow-pw

**type:** boolean
**default:** `true` if `authorized_keys` is empty, `false` otherwise

<a name="codecs"></a>

### codecs

**type:** mapping, see below
**default:** see below
**can be interactive:** no

Configure whether common restricted packages (including codecs) from [multiverse] should be installed.

#### install

**type:** boolean
**default:** `false`

Whether to install the ubuntu-restricted-addons package.

<a name="drivers"></a>

### drivers

**type:** mapping, see below
**default:** see below
**can be interactive:** yes

#### install

**type:** boolean
**default:** `false`

Whether to install the available third-party drivers.

<a name="snaps"></a>

### snaps

**type:** list
**default:** install no extra snaps
**can be interactive:** yes

A list of snaps to install. Each snap is represented as a mapping with required `name` and optional `channel` (defaulting to `stable`) and classic (defaulting to `false`) keys. For example:

<pre><code>snaps:
    - name: etcd
      channel: edge
      classic: false</code></pre>

<a name="debconf-selections"></a>

### debconf-selections

**type:** string
**default:** no config
**can be interactive:** no

The installer will update the target with debconf set-selection values. Users will need to be familiar with the package debconf options.

<a name="packages"></a>

### packages

**type:** list
**default:** no packages
**can be interactive:** no

A list of packages to install into the target system. More precisely, a list of strings to pass to "`apt-get install`", so this includes things like task selection (`dns-server^`) and installing particular versions of a package (`my-package=1-1`).

### kernel

**type:** mapping (mutually exclusive), see below
**default:** default kernel
**can be interactive:** no

Which kernel gets installed. Either the name of the package or the name of the flavor must be specified.

#### package

**type:** string

The name of the package, e.g., `linux-image-5.13.0-40-generic`

#### flavor

**type:** string

The flavor of the kernel, e.g., `generic` or `hwe`.

### timezone

**type:** string
**default:** no timezone
**can be interactive:** no

The timezone to configure on the system. The special value "geoip" can be used to query the timezone automatically over the network.

### updates

**type:** string (enumeration)
**default:** `security`
**can be interactive:** no

The type of updates that will be downloaded and installed after the system install.
Supported values are:

 * `security` -> download and install updates from the -security pocket
 * `all` -> also download and install updates from the -updates pocket

### shutdown

**type:** string (enumeration)
**default:** `reboot`
**can be interactive:** no

Request the system to poweroff or reboot automatically after the installation has finished.
Supported values are:

 * `reboot`
 * `poweroff`

<a name="late-commands"></a>

### late-commands

**type:** [command list](#commandlist)
**default:** no commands
**can be interactive:** no

Shell commands to run after the install has completed successfully and any updates and packages installed, just before the system reboots. They are run in the installer environment with the installed system mounted at `/target`. You can run `curtin in-target -- $shell_command` (with the version of subiquity released with 20.04 GA you need to specify this as `curtin in-target --target=/target -- $shell_command`) to run in the target system (similar to how plain `in-target` can be used in `d-i preseed/late_command`).

<a name="error-commands"></a>

### error-commands

**type:** [command list](#commandlist)
**default:** no commands
**can be interactive:** no

Shell commands to run after the install has failed. They are run in the installer environment, and the target system (or as much of it as the installer managed to configure) will be mounted at /target. Logs will be available at `/var/log/installer` in the live session.

<a name="reporting"></a>

### reporting

**type:** mapping
**default:** `type: print` which causes output on tty1 and any configured serial consoles
**can be interactive:** no

The installer supports reporting progress to a variety of destinations.  Note that this section is ignored if there are any [interactive sections](#interactive-sections); it only applies to fully automated installs.

The config, and indeed the implementation, is 90% the same as [that used by curtin](https://curtin.readthedocs.io/en/latest/topics/reporting.html).

Each key in the `reporting` mapping in the config defines a destination, where the `type` sub-key is one of:

**The rsyslog reporter does not yet exist**

 * **print**: print progress information on tty1 and any configured serial console. There is no other configuration.
 * **rsyslog**: report progress via rsyslog. The **destination** key specifies where to send output.
 * **webhook**: report progress via POSTing JSON reports to a URL. Accepts the same configuration as [curtin](https://curtin.readthedocs.io/en/latest/topics/reporting.html#webhook-reporter).
 * **none**: do not report progress. Only useful to inhibit the default output.

Examples:

The default configuration is:

<pre><code>reporting:
 builtin:
  type: print</code></pre>

Report to rsyslog:

<pre><code>reporting:
 central:
  type: rsyslog
  destination: @192.168.0.1</code></pre>

Suppress the default output:

<pre><code>reporting:
 builtin:
  type: none</code></pre>

Report to a curtin-style webhook:

<pre><code>reporting:
 hook:
  type: webhook
  endpoint: http://example.com/endpoint/path
  consumer_key: "ck_foo"
  consumer_secret: "cs_foo"
  token_key: "tk_foo"
  token_secret: "tk_secret"
  level: INFO</code></pre>

<a name="user-data"></a>

### user-data

**type:** mapping
**default:** `{}`
**can be interactive:** no

Provide cloud-init user-data which will be merged with the user-data the installer produces. If you supply this, you don't need to supply an [identity section](#identity) (but then it's your responsibility to make sure that you can log into the installed system!).
