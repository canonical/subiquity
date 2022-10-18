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

So you just want to try it out? Well we have [the page for you](/t/draft-automated-server-install-quickstart/16614).

## Creating an autoinstall config

When any system is installed using the server installer, an autoinstall file for repeating the install is created  at `/var/log/installer/autoinstall-user-data`.

# Translating a preseed file

If you have a preseed file already, the [autoinstall-generator](https://snapcraft.io/autoinstall-generator) snap can assist in translating that preseed data to an autoinstall file.  See this [discussion](https://discourse.ubuntu.com/t/autoinstall-generator-tool-to-help-with-creation-of-autoinstall-files-based-on-preseed/21334) for more details.

# The structure of an autoinstall config

The autoinstall config has [full documentation](/t/draft-automated-server-install-reference/16613).

Technically speaking the config is not defined as a textual format, but cloud-init config is usually provided as YAML so that is the syntax the documentation uses.

A minimal config is:

    version: 1
    identity:
        hostname: hostname
        username: username
        password: $crypted_pass

Here is an example file that shows off most features:

<pre><code><a href="/t/draft-automated-server-install-reference/16613#version">version</a>: 1
<a href="/t/draft-automated-server-install-reference/16613#reporting">reporting</a>:
    hook:
        type: webhook
        endpoint: http://example.com/endpoint/path
<a href="/t/draft-automated-server-install-reference/16613#early-commands">early-commands</a>:
    - ping -c1 198.162.1.1
<a href="/t/draft-automated-server-install-reference/16613#locale">locale</a>: en_US
<a href="/t/draft-automated-server-install-reference/16613#keyboard">keyboard</a>:
    layout: gb
    variant: dvorak
<a href="/t/draft-automated-server-install-reference/16613#network">network</a>:
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
<a href="/t/draft-automated-server-install-reference/16613#proxy">proxy</a>: http://squid.internal:3128/
<a href="/t/draft-automated-server-install-reference/16613#apt">apt</a>:
    primary:
        - arches: [default]
          uri: http://repo.internal/
    sources:
        my-ppa.list:
            source: "deb http://ppa.launchpad.net/curtin-dev/test-archive/ubuntu $RELEASE main"
            keyid: B59D 5F15 97A5 04B7 E230  6DCA 0620 BBCF 0368 3F77
<a href="/t/draft-automated-server-install-reference/16613#storage">storage</a>:
    layout:
        name: lvm
<a href="/t/draft-automated-server-install-reference/16613#identity">identity</a>:
    hostname: hostname
    username: username
    password: $crypted_pass
<a href="/t/draft-automated-server-install-reference/16613#ssh">ssh</a>:
    install-server: yes
    authorized-keys:
      - $key
    allow-pw: no
<a href="/t/draft-automated-server-install-reference/16613#snaps">snaps</a>:
    - name: go
      channel: 1.14/stable
      classic: true
<a href="/t/draft-automated-server-install-reference/16613#debconf-selections">debconf-selections</a>: |
    bind9      bind9/run-resolvconf    boolean false
<a href="/t/draft-automated-server-install-reference/16613#packages">packages</a>:
    - libreoffice
    - dns-server^
<a href="/t/draft-automated-server-install-reference/16613#user-data">user-data</a>:
    disable_root: false
<a href="/t/draft-automated-server-install-reference/16613#late-commands">late-commands</a>:
    - sed -ie 's/GRUB_TIMEOUT=.*/GRUB_TIMEOUT=30/' /target/etc/default/grub
<a href="/t/draft-automated-server-install-reference/16613#error-commands">error-commands</a>:
    - tar c /var/log/installer | nc 192.168.0.1 1000
</code></pre>

Many keys and values correspond straightforwardly to questions the installer asks (e.g. keyboard selection). See the reference for details of those that do not.

# Error handling

Progress through the installer is reported via the [`reporting`](/t/draft-automated-server-install-reference/16613#reporting) system, including errors. In addition, when a fatal error occurs, the [`error-commands`](/t/draft-automated-server-install-reference/16613#error-commands) are executed and the traceback printed to the console. The server then just waits.

# Possible future directions

We might want to extend the 'match specs' for disks to cover other ways of selecting disks.
