Firstboot
---------

Firstboot is a tui that runs on the device's getty interfaces when a
system has not yet been configured.  It displays the current network
configuration and allows user to modify that.  It also collects
user information used to create a local user and import ssh public keys


Getting Started
---------------

Install pre-reqs:

  % sudo apt-get update && sudo apt-get install qemu-system-x86 cloud-image-utils

Download the firstboot image and startup script

  % wget http://people.canonical.com/~rharper/firstboot/firstboot.sh
  % chmod +x ./firstboot.sh 
  % wget http://people.canonical.com/~rharper/firstboot/firstboot.raw.xz
  % unxz firstboot.raw.xz
  % ./firstboot.sh

This will launch the firstboot image under KVM using userspace networking
The main console will open in a new window, the serial console is available via
telnet session (telnet localhost 2447).


When firstboot displays the ssh URL, in the demo, since we're using qemu user
networking, we can't ssh directly to the VM, instead we redirect the guest's ssh
port 22 to host port 2222; this is a limitation of the demo.  When ssh'ing to
the guest, use:

  ssh -p 2222 <user>@localhost


How it works
------------

The firstboot program is launched after the getty service is available, and
disables getty on any tty and instead spawns the firstboot program.  It will
remain available until one of the firstboot instances successfully completes.
After completion, firstboot will disable itself and re-enable getty services.

firstboot is based on subiquity, just pulling out a few of the panels and
reusing certain parts.  The networking information is probed from the host
and allows user configuration.  After completion of configuration, firstboot
uses the ``ip`` command to apply the new network config to the network devices
present.  Long term, we'll supply network-config yaml to snappy or whatever 
network configuration tool will be present and be responsible for bringing
networking up to the desired state.

For identity, we collect realname, username, password (and crypt it), and a
"ssh_import_id" URL.  The ``ssh-import-id`` binary already supports both
launchpad (lp:) and github (gh:).  In the demo, I added mock SSO support (sso:)
and this would trigger a call out to snappy login or what ever the right tool
to initiate a connection to the SSO for authentication and retrieval of the
user's ssh keys.

After collecting the input, we run ``ip``, ``useradd`` and ``ssh-import-id``
and display the current config, including ssh url.  After selecting "Finish"
We restore the normal getty prompt from which the newly created user can login.
