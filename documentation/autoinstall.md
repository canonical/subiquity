## Introduction

Since version 20.04, the server installer supports automated installation mode (autoinstallation for short). You might also know this feature as *unattended*, *hands-off*, or *preseeded* installation.

Autoinstallation lets you answer all those configuration questions ahead of time with an *autoinstall config*, and lets the installation process run without any interaction.

## Differences from debian-installer preseeding

*Preseeds* are the way to automate an installer based on debian-installer (a.k.a. *d-i*).

Autoinstalls for the new server installer differ from preseeds in the following main ways:

 * The format is completely different (cloud-init config, usually YAML, vs. `debconf-set-selections` format).
 * When the answer to a question is not present in a preseed, d-i stops and asks the user for input. Autoinstalls are not like this: by default, if there is any autoinstall config at all, the installer takes the default for any unanswered question (and fails if there is no default).
    * You can designate particular sections in the config as "interactive", which means the installer will still stop and ask about those.

## Provide the autoinstall config via cloud-init

The autoinstall config is provided via cloud-init configuration, which is almost endlessly flexible. In most scenarios, the easiest way will be to provide user data [via the NoCloud datasource](https://cloudinit.readthedocs.io/en/latest/reference/datasources/nocloud.html).

The autoinstall config should be provided under the `autoinstall` key in the config. For example:

```yaml
#cloud-config
autoinstall:
  version: 1
  ...
```

## Run a truly automatic autoinstall

Even if a fully non-interactive autoinstall config is found, the server installer will ask for confirmation before writing to the disks unless `autoinstall` is present on the kernel command line. This is to make it harder to accidentally create a USB stick that will reformat the machine it is plugged into at boot. Many autoinstalls will be done via netboot, where the kernel command line is controlled by the netboot config -- just remember to put `autoinstall` in there!

### Quick start

So you just want to try it out? Well we have [the page for you](autoinstall-quickstart.md).

### Create an autoinstall config

When any system is installed using the server installer, an autoinstall file for repeating the install is created  at `/var/log/installer/autoinstall-user-data`.

### Translate a preseed file

If you have a preseed file already, the [autoinstall-generator snap](https://snapcraft.io/autoinstall-generator) can help translate that preseed data to an autoinstall file. See this discussion on the [autoinstall generator tool](https://discourse.ubuntu.com/t/autoinstall-generator-tool-to-help-with-creation-of-autoinstall-files-based-on-preseed/21334) for more details on how to set this up.

## The structure of an autoinstall config

The autoinstall config has [full documentation](autoinstall-reference.md).

Technically speaking, the config is not defined as a textual format, but cloud-init config is usually provided as YAML so that is the syntax the documentation uses. A minimal config consists of:

```yaml
version: 1
identity:
    hostname: hostname
    username: username
    password: $crypted_pass
```

However, here is a more complete example file that shows off most features:

<pre><code><a href="autoinstall-reference.md#version">version</a>: 1
<a href="autoinstall-reference.md#reporting">reporting</a>:
    hook:
        type: webhook
        endpoint: http://example.com/endpoint/path
<a href="autoinstall-reference.md#early-commands">early-commands</a>:
    - ping -c1 198.162.1.1
<a href="autoinstall-reference.md#locale">locale</a>: en_US
<a href="autoinstall-reference.md#keyboard">keyboard</a>:
    layout: gb
    variant: dvorak
<a href="autoinstall-reference.md#network">network</a>:
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
<a href="autoinstall-reference.md#proxy">proxy</a>: http://squid.internal:3128/
<a href="autoinstall-reference.md#apt">apt</a>:
    primary:
        - arches: [default]
          uri: http://repo.internal/
    sources:
        my-ppa.list:
            source: "deb http://ppa.launchpad.net/curtin-dev/test-archive/ubuntu $RELEASE main"
            keyid: B59D 5F15 97A5 04B7 E230  6DCA 0620 BBCF 0368 3F77
<a href="autoinstall-reference.md#storage">storage</a>:
    layout:
        name: lvm
<a href="autoinstall-reference.md#identity">identity</a>:
    hostname: hostname
    username: username
    password: $crypted_pass
<a href="autoinstall-reference.md#ssh">ssh</a>:
    install-server: yes
    authorized-keys:
      - $key
    allow-pw: no
<a href="autoinstall-reference.md#snaps">snaps</a>:
    - name: go
      channel: 1.14/stable
      classic: true
<a href="autoinstall-reference.md#debconf-selections">debconf-selections</a>: |
    bind9      bind9/run-resolvconf    boolean false
<a href="autoinstall-reference.md#packages">packages</a>:
    - libreoffice
    - dns-server^
<a href="autoinstall-reference.md#user-data">user-data</a>:
    disable_root: false
<a href="autoinstall-reference.md#late-commands">late-commands</a>:
    - sed -ie 's/GRUB_TIMEOUT=.\*/GRUB_TIMEOUT=30/' /target/etc/default/grub
<a href="autoinstall-reference.md#error-commands">error-commands</a>:
    - tar c /var/log/installer | nc 192.168.0.1 1000
</code></pre>

Many keys and values correspond straightforwardly to questions the installer asks (e.g. keyboard selection). See the reference for details of those that do not.

## Error handling

Progress through the installer is reported via [the `reporting` system](/t/automated-server-install-reference/16613#reporting), including errors. In addition, when a fatal error occurs, the [`error-commands`](/t/automated-server-install-reference/16613#error-commands) are executed and the traceback printed to the console. The server then just waits.

## Interactions between Autoinstall and Cloud-init

### Delivery of Autoinstall

Cloud-config can be used to deliver the autoinstall data to the installation environment. The [autoinstall quickstart](/t/automated-server-install-quickstart/16614) has an example of [writing the autoinstall config](/t/automated-server-install-quickstart/16614#write-your-autoinstall-config).

Note that autoinstall is processed by Subiquity (not cloud-init), so please direct defects in autoinstall behavior and [bug reports to Subiquity](https://bugs.launchpad.net/subiquity/+filebug).

### The installation environment

At install time, the live-server environment is just that: a live but ephemeral copy of Ubuntu Server.  This means that cloud-init is present and running in that environment, and existing methods of interacting with cloud-init can be used to configure the live-server ephemeral environment. For example, any #cloud-config user data keys are presented to the live-server containing [`ssh_import_id`]( https://cloudinit.readthedocs.io/en/latest/reference/modules.html#ssh-import-id), then SSH keys will be added to the `authorized_keys` list for the ephemeral environment.

### First boot configuration of the target system

Autoinstall data may optionally contain a [user data sub-section](/t/automated-server-install-reference/16613#user-data), which is cloud-config data that is used to configure the target system on first boot.

Subiquity itself delegates some configuration items to cloud-init, and these items are processed on first boot.

Starting with Ubuntu 22.10, once cloud-init has performed this first boot configuration, it will disable itself as cloud-init completes configuration in the target system on first boot.

### Possible future directions

We might want to extend the 'match specs' for disks to cover other ways of selecting disks.
