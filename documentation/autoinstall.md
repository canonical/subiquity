# Automated Server Installs

## Introduction

The server installer for 20.04 supports a new mode of operation: automated installation, autoinstallation for short. You might also know this feature as unattended or handsoff or preseeded installation.

Autoinstallation lets you answer all those configuration questions ahead of time with an *autoinstall config* and lets the installation process run without any interaction.

## Differences from debian-installer preseeding

*preseeds* are the way to automate an installer based on debian-installer (aka d-i).

autoinstalls for the new server installer differ from preseeds in the following main ways:

 * the format is completely different (cloud-init config, usually yaml, vs debconf-set-selections format)
 * when the answer to a question is not present in a preseed, d-i   stops and asks the user for input. autoinstalls are not like this:   by default, if there is any autoinstall config at all, the   installer takes the default for any unanswered question (and fails if there is no default).
    * You can designate particular sections in   the config as "interactive", which means the installer will still stop and ask about those.

## Providing the autoinstall config

The autoinstall config is provided via cloud-init configuration, which is almost endlessly flexible. In most scenarios the easiest way will be to provide user-data via the [nocloud](https://cloudinit.readthedocs.io/en/latest/topics/datasources/nocloud.html) data source.

The autoinstall config should be provided under the `autoinstall` key in the config. For example:

    #cloud-config
    autoinstall:
      version: 1
      ...

## Running a truly automatic autoinstall

Even if a fully noninteractive autoinstall config is found, the server installer will ask for confirmation before writing to the disks unless `autoinstall` is present on the kernel command line. This is to make it harder to accidentally create a USB stick that will reformat a machine it is plugged into at boot. Many autoinstalls will be done via netboot, where the kernel command line is controlled by the netboot config -- just remember to put `autoinstall` in there!

## Quick start

So you just want to try it out? Well we have [the page for you](autoinstall-quickstart.md).

## Creating an autoinstall config

When any system is installed using the server installer, an autoinstall file for repeating the install is created  at `/var/log/installer/autoinstall-user-data`.

# Translating a preseed file

If you have a preseed file already, the [autoinstall-generator](https://snapcraft.io/autoinstall-generator) snap can assist in translating that preseed data to an autoinstall file.  See this [discussion](https://discourse.ubuntu.com/t/autoinstall-generator-tool-to-help-with-creation-of-autoinstall-files-based-on-preseed/21334) for more details.

# The structure of an autoinstall config

The autoinstall config has [full documentation](autoinstall-reference.md).

Technically speaking the config is not defined as a textual format, but cloud-init config is usually provided as YAML so that is the syntax the documentation uses.

A minimal config is:

    version: 1
    identity:
        hostname: hostname
        username: username
        password: $crypted_pass

Here is an example file that shows off most features:

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
    - sed -ie 's/GRUB_TIMEOUT=.*/GRUB_TIMEOUT=30/' /target/etc/default/grub
<a href="autoinstall-reference.md#error-commands">error-commands</a>:
    - tar c /var/log/installer | nc 192.168.0.1 1000
</code></pre>

Many keys and values correspond straightforwardly to questions the installer asks (e.g. keyboard selection). See the reference for details of those that do not.

# Error handling

Progress through the installer is reported via the [`reporting`](autoinstall-reference.md#reporting) system, including errors. In addition, when a fatal error occurs, the [`error-commands`](autoinstall-reference.md#error-commands) are executed and the traceback printed to the console. The server then just waits.

# Interactions between Autoinstall and Cloud-init

## Delivery of Autoinstall

Cloud-config can be used to deliver the Autoinstall data to the installation environment. The [autoinstall quickstart](autoinstall-quickstart.md) has an [example](autoinstall-quickstart.md#write-your-autoinstall-config) demonstrating this.

Note that Autoinstall is processed by Subiquity (not Cloud-init), so please direct defects in Autoinstall behavior to [Subiquity](https://bugs.launchpad.net/subiquity/+filebug).

## The installation environment

At install time, the live-server environment is just that, a live but ephemeral copy of Ubuntu Server.  This means that Cloud-init is present and running in that environment, and existing methods of interacting with Cloud-init can affect the live-server.  For example, if a cloud-config is presented to the live-server containing [`ssh_import_id`](https://cloudinit.readthedocs.io/en/latest/topics/modules.html?highlight=ssh#ssh-import-id), then ssh keys will be added to the authorized_keys list for the installation environment.

## First boot configuation of the target system

Autoinstall data may optionally contain a [user-data](autoinstall-reference.md#user-data) section, which is cloud-config data that is configuring the target system.

Subiquity itself delegates some configuration items to Cloud-init, and these items are processed on first boot.

Starting with Ubuntu 22.10, once Cloud-init has performed this first boot configuration, it will disable itself.

# Possible future directions

We might want to extend the 'match specs' for disks to cover other ways of selecting disks.
