Creating autoinstall configuration
===================================

When any system is installed using the Ubuntu installer, an autoinstall file for repeating the installation is created at :code:`/var/log/installer/autoinstall-user-data`. :ref:`providing-autoinstall` describes the two ways of delivering this autoinstall configuration to Ubuntu installer.


The structure of an autoinstall configuration
---------------------------------------------

Go to the :ref:`ai` for full details on the supported autoinstall directives.

.. code-block:: yaml

    #cloud-config
    autoinstall:
        version: 1
        identity:
            hostname: hostname
            username: username
            password: $crypted_pass

Here is an example file that shows most of the autoinstall directives:

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
