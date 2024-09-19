.. _testing-secure-boot:

How to test Secure Boot
=======================

.. This content is from:
.. https://wiki.ubuntu.com/UEFI/SecureBoot/Testing

.. important:: This article is for development purposes and a WIP. Don't use unless you know you're doing!

Testing infrastructure uses the Security team's `Testing environment <https://wiki.ubuntu.com/SecurityTeam/TestingEnvironment>`_.


.. _vm-installation-and-preparation:

VM installation and preparation
-------------------------------

#. Obtain an OVMF image capable of performing Secure Boot in one of the following ways:

   - Install the :pkg:`ovmf` package
   - `Compile it yourself <https://wiki.ubuntu.com/UEFI/EDK2>`_

#. Verify the symbolic link from :file:`/usr/share/ovmf/OVMF.fd` to :file:`/usr/share/qemu/OVMF.fd`.

#. Install Ubuntu using the Secure Boot capable UEFI OVMF firmware (downloaded as :file:`bios.bin`):

   .. code:: none

     uvt new --loader=OVMF.fd --with-ovmf-uefi xenial amd64 sb

   This can also be performed with the :command:`virt-install` command:

   .. code:: none

     virt-install --connect=qemu:///system --name=sb-xenial-amd64 --arch=x86_64 --ram=2048 \
     --disk=path=<path to>/sb-xenial-amd64.qcow2,size=8,format=qcow2,bus=ide,sparse=True \
     --virt-type=kvm --accelerate --hvm --cdrom=<path to>/xenial-desktop-amd64.iso \
     --os-type=linux --os-variant=generic26 --graphics=vnc --network=network=default,model=virtio \
     --video=cirrus --noreboot --boot=loader=OVMF.fd

Both of the above commands create the ``sb-xenial-amd64`` machine. Note that when using :command:`uvt`, there is a limitation in that a preseeded ISO cannot be used. :command:`uvt` skips the postinstall phase and you need to perform the installation manually. You know you are using the OVMF EFI image if the machine comes up with 'Try Ubuntu' (i.e., not the graphical installation). Using the manual partitioner to create a 250M EFI partition as the first partition and then setting up a :file:`/` and swap partition is known to work.

Caveats:

- The installer doesn't reboot after installation without pressing :kbd:`Enter`.
- On Ubuntu releases earlier than 16.04: on reboot and all boots, you must go into the EFI config screen to boot from a file off the disk. E.g., from the main EFI configuration screen:

  .. code:: none

    - Boot Maintenance Manager ->
      - Boot From File ->
        - NO VOLUME LABEL,[!PciRoot(0x0)/Pci(0x1,0x1)/Ata(Primary,Master,0x0)/HD(1,GPT,...)] ->
          - <EFI> ->
            - <ubuntu> ->
              - grubx64.efi

  This behaviour can be changed by booting into the VM and then copying the appropriate files to :file:`/boot/efi/EFI/BOOT/BOOTX64.EFI`. E.g.:

  - For GRUB2 only, copy :file:`/boot/efi/EFI/ubuntu/grubx64.efi` to :file:`/boot/efi/EFI/BOOT/BOOTX64.EFI`.

  - For the shim, copy :file:`/boot/efi/EFI/ubuntu/shimx64.efi` to :file:`/boot/efi/EFI/BOOT/BOOTX64.EFI` and then copy :file:`/boot/efi/EFI/ubuntu/grubx64.efi` and :file:`grub.cfg` to :file:`/boot/efi/EFI/BOOT/`. Note that this document assumes you are using the 'Boot From File' method.

- Suggested post-installation steps (as the postinstall is not running via :command:`uvt`):

  - Run:

    .. code:: none

       sudo apt-get install openssh-server screen vim gnome-panel

  - Use :command:`ssh-copy-id` to copy your key over.
  - Optionally, update :file:`sources.list` for your mirror.

- When using :command:`uvt`, the initial pristine snapshot is not created. After setting up, use:

  .. code:: none

     uvt snapshot sb-quantal-amd64

- As the firmware needs to be able to interact with the hardware and is limited in what it supports, the following are used when using :command:`uvt`:

  - IDE disks (can't use virtio)
  - Cirrus video driver

- The ``virtio`` network driver is used. If you want to try PXE booting via EFI, you may need to change this.

See `OVMF <https://wiki.ubuntu.com/UEFI/OVMF>`_ for other ways of using the :file:`OVMF` file.


.. _efi-shell:

EFI shell
~~~~~~~~~

To go into the EFI shell, adjust the ``Boot Order`` in ``Boot options``:

.. code:: none

    - Boot Maintenance Manager ->
      - Boot Options ->
        - Change Boot Order ->
          - Highlight the list, press Enter, go to 'EFI Internal Shell' then press
            '+' until it is above 'EFI Hard Drive'. Press Enter, then select
            Commit Changes and Exit

At this point, press :kbd:`Esc` until you get to the main EFI configuration menu and click :guilabel:`Continue`. This boots the shell. Enter ``exit`` to return to the EFI configuration menu. Useful commands:

``Shell> ls fs0:\``
  Directory listing corresponding to :file:`/boot/efi`

``Shell> ls fs0:\EFI\ubuntu\``
  Directory listing of where our bootloaders are

``Shell> fs0:\EFI\ubuntu\grubx64.efi\``
  Launch GRUB2 bootloader

``Shell> fs0:\EFI\ubuntu\shimx64.efi\``
  Launch shim bootloader

``Shell> fs0:\EFI\ubuntu\efilinux.efi -f 0:\EFI\ubuntu\vmlinuz initrd=0:\EFI\ubuntu\initrd root=/dev/sda3 quiet splash``
  Launch efilinux bootloader

.. note:: After booting the system via the EFI shell, the OVMF firmware defaults to EFI Hard Drive and does not allow access to the shell. You have to do a cold reboot to enter the shell again.


.. _keeping-the-vm-up-to-date:

Keeping the VM up-to-date
~~~~~~~~~~~~~~~~~~~~~~~~~

The :command:`uvt update` command does not work because the boot process requires manual intervention. As such, keeping the VM up to date consists of the following steps:

#. Start the VM:

   .. code:: none

     sudo uvt start [-rf] <vmname>

#. Select the image to boot:

   .. code:: none

     uvt cmd -r -p <vmprefix> 'apt-get update && apt-get -y --force-yes dist-upgrade && apt-get autoremove --purge'

#.

   .. code:: none

     uvt stop <vmname>

#.

   .. code:: none

     uvt snapshot <vmname>


.. _assisted-secure-boot-vm-setup:

Assisted Secure Boot VM setup
-----------------------------


.. _bootloader-signed-with-user-key:

Bootloader signed with user key
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This emulates a configuration where a user or enterprise is using their own keys in PK, KEK, and DB and follow the procedures in `sbkeysync & maintaining uefi key databases <http://jk.ozlabs.org/docs/sbkeysync-maintaing-uefi-key-databases/>`_ . This configuration allows the greatest flexibility in testing as we control PK and KEK, so we can update all aspects of Secure Boot as needed. The key database is configured with (each entry in firmware has the same GUID):

- User key in PK
- User key in KEK
- User key in DB

Steps to configure:

#. Boot an OVMF virtual UEFI machine (see :ref:`vm-installation-and-preparation`).
#. Install required packages:

   .. code:: none

     sudo apt-get install sbsigntool openssl grub-efi-amd64-signed fwts linux-signed-generic

#. Install the signed bootloader:

   .. code:: none

     sudo grub-install --uefi-secure-boot

#. Reboot the VM and choose :guilabel:`Boot from File` as above (continue to use :file:`grubx64.efi`).

#. **FIXME:** Download `sb-setup and keys <https://git.launchpad.net/qa-regression-testing/tree/notes_testing/secure-boot>`_ to :file:`/tmp/sb-setup` and :file:`/tmp/keys`.

#. Enrol the user keys (output may vary):

   .. code:: none

    /tmp/sb-setup enroll
    Creating keystore...
      mkdir '/etc/secureboot/keys'
      mkdir '/etc/secureboot/keys/PK'
      mkdir '/etc/secureboot/keys/KEK'
      mkdir '/etc/secureboot/keys/db'
      mkdir '/etc/secureboot/keys/dbx'
    done

    Creating keys... done

    Generating key updates for PK...
      using GUID=1d5bd2fb-f597-4315-b3bc-dfe84b594ce7
      creating EFI_SIGNATURE_LIST (test-cert.der.siglist)...
      creating signed update (test-cert.der.siglist.PK.signed)...
    done
    Generating key updates for KEK...
      using GUID=1d5bd2fb-f597-4315-b3bc-dfe84b594ce7
      creating EFI_SIGNATURE_LIST (test-cert.der.siglist)...
      creating signed update (test-cert.der.siglist.KEK.signed)...
    done
    Generating key updates for db...
      using GUID=1d5bd2fb-f597-4315-b3bc-dfe84b594ce7
      creating EFI_SIGNATURE_LIST (test-cert.der.siglist)...
      creating signed update (test-cert.der.siglist.db.signed)...
    done
    Initializing keystore...
      adding to /etc/secureboot/keys/PK/
      adding to /etc/secureboot/keys/KEK/
      adding to /etc/secureboot/keys/db/
    done

    Filesystem keystore:
      /etc/secureboot/keys/db/test-cert.der.siglist.db.signed [2116 bytes]
      /etc/secureboot/keys/KEK/test-cert.der.siglist.KEK.signed [2116 bytes]
      /etc/secureboot/keys/PK/test-cert.der.siglist.PK.signed [2116 bytes]
    firmware keys:
      PK:
      KEK:
      db:
      dbx:
    filesystem keys:
      PK:
        /CN=test-key
          from /etc/secureboot/keys/PK/test-cert.der.siglist.PK.signed
      KEK:
        /CN=test-key
          from /etc/secureboot/keys/KEK/test-cert.der.siglist.KEK.signed
      db:
        /CN=test-key
          from /etc/secureboot/keys/db/test-cert.der.siglist.db.signed
      dbx:
    New keys in filesystem:
      /etc/secureboot/keys/db/test-cert.der.siglist.db.signed
      /etc/secureboot/keys/KEK/test-cert.der.siglist.KEK.signed
      /etc/secureboot/keys/PK/test-cert.der.siglist.PK.signed
    Commit to keystore? (y|N) y
    Filesystem keystore:
      /etc/secureboot/keys/db/test-cert.der.siglist.db.signed [2116 bytes]
      /etc/secureboot/keys/KEK/test-cert.der.siglist.KEK.signed [2116 bytes]
      /etc/secureboot/keys/PK/test-cert.der.siglist.PK.signed [2116 bytes]
    firmware keys:
      PK:
      KEK:
      db:
      dbx:
    filesystem keys:
      PK:
        /CN=test-key
          from /etc/secureboot/keys/PK/test-cert.der.siglist.PK.signed
      KEK:
        /CN=test-key
          from /etc/secureboot/keys/KEK/test-cert.der.siglist.KEK.signed
      db:
        /CN=test-key
          from /etc/secureboot/keys/db/test-cert.der.siglist.db.signed
      dbx:
    New keys in filesystem:
      /etc/secureboot/keys/db/test-cert.der.siglist.db.signed
      /etc/secureboot/keys/KEK/test-cert.der.siglist.KEK.signed
      /etc/secureboot/keys/PK/test-cert.der.siglist.PK.signed
    Inserting key update /etc/secureboot/keys/db/test-cert.der.siglist.db.signed into db
    Inserting key update /etc/secureboot/keys/KEK/test-cert.der.siglist.KEK.signed into KEK
    Inserting key update /etc/secureboot/keys/PK/test-cert.der.siglist.PK.signed into PK
    Signing '/boot/efi/EFI/ubuntu/grubx64.efi'
    warning: overwriting existing signature

#. Reboot and verify Secure Boot is enabled:

   .. code:: none

    - Device Manager ->
      - Secure Boot Configuration ->
        - Verify 'Attempt Secure Boot' is selected and 'Secure Boot Mode' is in
          'Standard Mode' ('Custom Mode' is also ok)
        - Change 'Secure Boot Mode' to 'Custom Mode' by highlighting 'Standard
          Mode' and pressing 'Enter'
        - Select Custom Boot Options ->
          - PK Options ->
            - Verify 'Enroll PK' is grayed out. Delete PK should have '[ ]' (or
              possibly a GUID).
            - Press Esc
          - KEK Options ->
            - Delete KEK ->
              - Verify GUID from sb-setup is listed
              - Press 'Esc', twice
          - DB Options
            - Delete signature ->
              - Verify GUID from sb-setup is listed
              - Press 'Esc', twice
          - DBX Options
            - Delete signature ->
              - Verify no [[GUIDs]] are listed
              - Press 'Esc', twice


#. Press :kbd:`Esc` until at the main EFI configure screen, then :guilabel:`Boot from File` normally (notice now there is a :file:`grubx64.efi.bak` listed -- this is the :file:`grubx64.efi` as installed by :command:`sudo grub-install --uefi-secure-boot`. I.e., the one signed with Canonical's key).

#. Verify the machine booted with Secure Boot (you can also use :command:`sbsigdb` from newer versions of ``sbsigntool`` if it is available):

   .. code:: none

      sudo fwts uefidump - | grep Secure
      Name: [[SecureBoot]].
        Value: 0x01 (Secure Boot Mode On).

   In the above, a CA is setup in :file:`/etc/secureboot/key-material` (private key: :file:`test-key.rsa`, public pem: :file:`test-cert.pem`, public der: :file:`test-cert.der`). A keystore is created in :file:`/etc/secureboot/keys/` and signed updates (using the keys in :file:`/etc/secureboot/key-material`) are created for PK, KEK and DB.


.. _shim-bootloader-signed-with-microsoft-key:

Shim bootloader signed with Microsoft key
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This is the expected configuration for new machines with default hardware and has Microsoft keys in KEK and DB (user key still in PK and KEK). The key database configuration is with (user key in PK and KEK has the same GUID, each Microsoft key has a different GUID):

- User key in PK
- User key and 'Microsoft Corporation KEK CA' key in KEK
- 'Microsoft Corporation UEFI CA' key and 'Microsoft Windows Production PCA' key in DB

Steps to configure:

#. Boot an OVMF virtual UEFI machine (see :ref:`vm-installation-and-preparation`).
#. Install some packages:

   .. code:: none

      sudo apt-get install sbsigntool openssl grub-efi-amd64-signed \
                   fwts shim-signed linux-signed-generic

#. Install the signed bootloader:

   .. code:: none

      sudo grub-install --uefi-secure-boot

#. Reboot the VM and :guilabel:`Boot from File` as above, except choose :file:`shimx64.efi` instead of :file:`grubx64.efi`.

#. **FIXME:** Download `sb-setup and keys <https://git.launchpad.net/qa-regression-testing/tree/notes_testing/secure-boot>`_ to :file:`/tmp/sb-setup` and :file:`/tmp/keys`.

#. Enrol the keys (output may vary):

   .. code:: none

      /tmp/sb-setup enroll microsoft
      Creating keystore...
        mkdir '/etc/secureboot/keys'
        mkdir '/etc/secureboot/keys/PK'
        mkdir '/etc/secureboot/keys/KEK'
        mkdir '/etc/secureboot/keys/db'
        mkdir '/etc/secureboot/keys/dbx'
      done

      Creating keys... done

      Generating key updates for PK...
        using GUID=2b6a3c26-eeca-405d-bdc1-1e8c133253e1
        creating EFI_SIGNATURE_LIST (test-cert.der.siglist)...
        creating signed update (test-cert.der.siglist.PK.signed)...
      done
      Generating key updates for KEK...
        using GUID=2b6a3c26-eeca-405d-bdc1-1e8c133253e1
        creating EFI_SIGNATURE_LIST (test-cert.der.siglist)...
        creating signed update (test-cert.der.siglist.KEK.signed)...
      done
      Generating key updates for KEK...
        using GUID=dc072709-eb81-4b97-b1c1-3c48dc4202e1
        creating EFI_SIGNATURE_LIST (microsoft-kekca-public.der.siglist)...
        creating signed update (microsoft-kekca-public.der.siglist.KEK.signed)...
      done
      Generating key updates for db...
        using GUID=7fbf5694-f148-4051-8bd2-f36794ee2a54
        creating EFI_SIGNATURE_LIST (microsoft-pca-public.der.siglist)...
        creating signed update (microsoft-pca-public.der.siglist.db.signed)...
      done
      Generating key updates for db...
        using GUID=68386fb9-f8a6-4bfa-8868-adfd534a628a
        creating EFI_SIGNATURE_LIST (microsoft-uefica-public.der.siglist)...
        creating signed update (microsoft-uefica-public.der.siglist.db.signed)...
      done
      Initializing keystore...
        adding to /etc/secureboot/keys/PK/
        adding to /etc/secureboot/keys/KEK/
        adding to /etc/secureboot/keys/db/
      done

      Filesystem keystore:
        /etc/secureboot/keys/db/microsoft-pca-public.der.siglist.db.signed [2850 bytes]
        /etc/secureboot/keys/db/microsoft-uefica-public.der.siglist.db.signed [2907 bytes]
        /etc/secureboot/keys/KEK/test-cert.der.siglist.KEK.signed [2116 bytes]
        /etc/secureboot/keys/KEK/microsoft-kekca-public.der.siglist.KEK.signed [2867 bytes]
        /etc/secureboot/keys/PK/test-cert.der.siglist.PK.signed [2116 bytes]
      firmware keys:
        PK:
        KEK:
        db:
        dbx:
      filesystem keys:
        PK:
          /CN=test-key
            from /etc/secureboot/keys/PK/test-cert.der.siglist.PK.signed
        KEK:
          /C=US/ST=Washington/L=Redmond/O=Microsoft Corporation/CN=Microsoft Corporation KEK CA 2011
            from /etc/secureboot/keys/KEK/microsoft-kekca-public.der.siglist.KEK.signed
          /CN=test-key
            from /etc/secureboot/keys/KEK/test-cert.der.siglist.KEK.signed
        db:
          /C=US/ST=Washington/L=Redmond/O=Microsoft Corporation/CN=Microsoft Corporation UEFI CA 2011
            from /etc/secureboot/keys/db/microsoft-uefica-public.der.siglist.db.signed
          /C=US/ST=Washington/L=Redmond/O=Microsoft Corporation/CN=Microsoft Windows Production PCA 2011
            from /etc/secureboot/keys/db/microsoft-pca-public.der.siglist.db.signed
        dbx:
      New keys in filesystem:
        /etc/secureboot/keys/db/microsoft-pca-public.der.siglist.db.signed
        /etc/secureboot/keys/db/microsoft-uefica-public.der.siglist.db.signed
        /etc/secureboot/keys/KEK/test-cert.der.siglist.KEK.signed
        /etc/secureboot/keys/KEK/microsoft-kekca-public.der.siglist.KEK.signed
        /etc/secureboot/keys/PK/test-cert.der.siglist.PK.signed
      Commit to keystore? (y|N) y
      Filesystem keystore:
        /etc/secureboot/keys/db/microsoft-pca-public.der.siglist.db.signed [2850 bytes]
        /etc/secureboot/keys/db/microsoft-uefica-public.der.siglist.db.signed [2907 bytes]
        /etc/secureboot/keys/KEK/test-cert.der.siglist.KEK.signed [2116 bytes]
        /etc/secureboot/keys/KEK/microsoft-kekca-public.der.siglist.KEK.signed [2867 bytes]
        /etc/secureboot/keys/PK/test-cert.der.siglist.PK.signed [2116 bytes]
      firmware keys:
        PK:
        KEK:
        db:
        dbx:
      filesystem keys:
        PK:
          /CN=test-key
            from /etc/secureboot/keys/PK/test-cert.der.siglist.PK.signed
        KEK:
          /C=US/ST=Washington/L=Redmond/O=Microsoft Corporation/CN=Microsoft Corporation KEK CA 2011
            from /etc/secureboot/keys/KEK/microsoft-kekca-public.der.siglist.KEK.signed
          /CN=test-key
            from /etc/secureboot/keys/KEK/test-cert.der.siglist.KEK.signed
        db:
          /C=US/ST=Washington/L=Redmond/O=Microsoft Corporation/CN=Microsoft Corporation UEFI CA 2011
            from /etc/secureboot/keys/db/microsoft-uefica-public.der.siglist.db.signed
          /C=US/ST=Washington/L=Redmond/O=Microsoft Corporation/CN=Microsoft Windows Production PCA 2011
            from /etc/secureboot/keys/db/microsoft-pca-public.der.siglist.db.signed
        dbx:
      New keys in filesystem:
        /etc/secureboot/keys/db/microsoft-pca-public.der.siglist.db.signed
        /etc/secureboot/keys/db/microsoft-uefica-public.der.siglist.db.signed
        /etc/secureboot/keys/KEK/test-cert.der.siglist.KEK.signed
        /etc/secureboot/keys/KEK/microsoft-kekca-public.der.siglist.KEK.signed
        /etc/secureboot/keys/PK/test-cert.der.siglist.PK.signed
      Inserting key update /etc/secureboot/keys/db/microsoft-pca-public.der.siglist.db.signed into db
      Inserting key update /etc/secureboot/keys/db/microsoft-uefica-public.der.siglist.db.signed into db
      Inserting key update /etc/secureboot/keys/KEK/test-cert.der.siglist.KEK.signed into KEK
      Inserting key update /etc/secureboot/keys/KEK/microsoft-kekca-public.der.siglist.KEK.signed into KEK
      Inserting key update /etc/secureboot/keys/PK/test-cert.der.siglist.PK.signed into PK
      Skipping bootloader signing for 'microsoft'

#. Reboot and verify Secure Boot is enabled and configured like :ref:`bootloader-signed-with-user-key`, except with:

   - 2 different keys in KEK (should match GUIDs for KEK from sb-setup)
   - 2 different keys in db (should match GUIDs for db from sb-setup)

#. :guilabel:`Boot from File` normally (notice :file:`shimx64.efi` and :file:`grubx64.efi` are listed -- this is the :file:`grubx64.efi` as installed by :command:`sudo grub-install --uefi-secure-boot`. I.e., the one signed with Canonical's key).

#. Verify the machine booted with Secure Boot (you can also use :command:`sbsigdb` from newer versions of ``sbsigntool`` if it is available):

   .. code:: none

        sudo fwts uefidump - | grep Secure
        Name: [[SecureBoot]].
          Value: 0x01 (Secure Boot Mode On).

#. Reboot and try to boot :file:`grubx64.efi` (i.e., the one signed with Canonical's key). This should fail to boot (when you press :kbd:`Enter` to select it, nothing happens).


.. _bootloader-signed-with-canonical-key:

Bootloader signed with Canonical key
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This emulates a configuration that supports machines with Canonical's key in KEK and DB (user key still in PK and KEK). The key database is configured with (user key in PK and KEK has the same GUID, Canonical key in KEK and db has the same GUID):

- User key in PK
- User key and 'Canonical Ltd. Master Certificate Authority' key in KEK
- 'Canonical Ltd. Master Certificate Authority' key in DB

Steps to configure:

#. Boot an OVMF virtual UEFI machine (see :ref:`vm-installation-and-preparation`).
#. Install required packages:

   .. code:: none

     sudo apt-get install sbsigntool openssl grub-efi-amd64-signed \
                  fwts linux-signed-generic

#. Install the signed bootloader:

   .. code:: none

     sudo grub-install --uefi-secure-boot

#. Reboot the VM and :guilabel:`Boot from File` as above.

#. **FIXME:** Download `sb-setup and keys <https://git.launchpad.net/qa-regression-testing/tree/notes_testing/secure-boot>`_ to :file:`/tmp/sb-setup` and :file:`/tmp/keys`.

#. Enrol the keys (output may vary):

   .. code:: none

      /tmp/sb-setup enroll canonical
        mkdir '/etc/secureboot/keys'
        mkdir '/etc/secureboot/keys/PK'
        mkdir '/etc/secureboot/keys/KEK'
        mkdir '/etc/secureboot/keys/db'
        mkdir '/etc/secureboot/keys/dbx'
      done

      Creating keys... done

      Generating key updates for PK...
        using GUID=55077d9d-6ca8-427a-9291-c60425c676e2
        creating EFI_SIGNATURE_LIST (test-cert.der.siglist)...
        creating signed update (test-cert.der.siglist.PK.signed)...
      done
      Generating key updates for KEK...
        using GUID=55077d9d-6ca8-427a-9291-c60425c676e2
        creating EFI_SIGNATURE_LIST (test-cert.der.siglist)...
        creating signed update (test-cert.der.siglist.KEK.signed)...
      done
      Generating key updates for KEK...
        using GUID=6a43e12f-b589-40c3-a332-a15eac86e3f5
        creating EFI_SIGNATURE_LIST (canonical-master-public.der.siglist)...
        creating signed update (canonical-master-public.der.siglist.KEK.signed)...
      done
      Generating key updates for db...
        using GUID=6a43e12f-b589-40c3-a332-a15eac86e3f5
        creating EFI_SIGNATURE_LIST (canonical-master-public.der.siglist)...
        creating signed update (canonical-master-public.der.siglist.db.signed)...
      done
      Initializing keystore...
        adding to /etc/secureboot/keys/PK/
        adding to /etc/secureboot/keys/KEK/
        adding to /etc/secureboot/keys/db/
      done

      Filesystem keystore:
        /etc/secureboot/keys/db/canonical-master-public.der.siglist.db.signed [2431 bytes]
        /etc/secureboot/keys/KEK/canonical-master-public.der.siglist.KEK.signed [2431 bytes]
        /etc/secureboot/keys/KEK/test-cert.der.siglist.KEK.signed [2116 bytes]
        /etc/secureboot/keys/PK/test-cert.der.siglist.PK.signed [2116 bytes]
      firmware keys:
        PK:
        KEK:
        db:
        dbx:
      filesystem keys:
        PK:
          /CN=test-key
            from /etc/secureboot/keys/PK/test-cert.der.siglist.PK.signed
        KEK:
          /CN=test-key
            from /etc/secureboot/keys/KEK/test-cert.der.siglist.KEK.signed
          /C=GB/ST=Isle of Man/L=Douglas/O=Canonical Ltd./CN=Canonical Ltd. Master Certificate Authority
            from /etc/secureboot/keys/KEK/canonical-master-public.der.siglist.KEK.signed
        db:
          /C=GB/ST=Isle of Man/L=Douglas/O=Canonical Ltd./CN=Canonical Ltd. Master Certificate Authority
            from /etc/secureboot/keys/db/canonical-master-public.der.siglist.db.signed
        dbx:
      New keys in filesystem:
        /etc/secureboot/keys/db/canonical-master-public.der.siglist.db.signed
        /etc/secureboot/keys/KEK/canonical-master-public.der.siglist.KEK.signed
        /etc/secureboot/keys/KEK/test-cert.der.siglist.KEK.signed
        /etc/secureboot/keys/PK/test-cert.der.siglist.PK.signed
      Commit to keystore? (y|N) y
      Filesystem keystore:
        /etc/secureboot/keys/db/canonical-master-public.der.siglist.db.signed [2431 bytes]
        /etc/secureboot/keys/KEK/canonical-master-public.der.siglist.KEK.signed [2431 bytes]
        /etc/secureboot/keys/KEK/test-cert.der.siglist.KEK.signed [2116 bytes]
        /etc/secureboot/keys/PK/test-cert.der.siglist.PK.signed [2116 bytes]
      firmware keys:
        PK:
        KEK:
        db:
        dbx:
      filesystem keys:
        PK:
          /CN=test-key
            from /etc/secureboot/keys/PK/test-cert.der.siglist.PK.signed
        KEK:
          /CN=test-key
            from /etc/secureboot/keys/KEK/test-cert.der.siglist.KEK.signed
          /C=GB/ST=Isle of Man/L=Douglas/O=Canonical Ltd./CN=Canonical Ltd. Master Certificate Authority
            from /etc/secureboot/keys/KEK/canonical-master-public.der.siglist.KEK.signed
        db:
          /C=GB/ST=Isle of Man/L=Douglas/O=Canonical Ltd./CN=Canonical Ltd. Master Certificate Authority
            from /etc/secureboot/keys/db/canonical-master-public.der.siglist.db.signed
        dbx:
      New keys in filesystem:
        /etc/secureboot/keys/db/canonical-master-public.der.siglist.db.signed
        /etc/secureboot/keys/KEK/canonical-master-public.der.siglist.KEK.signed
        /etc/secureboot/keys/KEK/test-cert.der.siglist.KEK.signed
        /etc/secureboot/keys/PK/test-cert.der.siglist.PK.signed
      Inserting key update /etc/secureboot/keys/db/canonical-master-public.der.siglist.db.signed into db
      Inserting key update /etc/secureboot/keys/KEK/canonical-master-public.der.siglist.KEK.signed into KEK
      Inserting key update /etc/secureboot/keys/KEK/test-cert.der.siglist.KEK.signed into KEK
      Inserting key update /etc/secureboot/keys/PK/test-cert.der.siglist.PK.signed into PK
      Skipping bootloader signing for 'canonical'

#. Reboot and verify Secure Boot is enabled and configured like 'Bootloader signed with user key' above, except with:

   - 2 different keys in KEK (should match GUIDs for KEK from sb-setup)
   - 2 different keys in db (should match GUIDs for db from sb-setup)

#. :guilabel:`Boot from File` normally (notice only :file:`grubx64.efi` listed -- this is the :file:`grubx64.efi` as installed by :command:`sudo grub-install --uefi-secure-boot`. I.e., the one signed with Canonical's key).

#. Verify the machine booted with Secure Boot (note, can also use :command:`sbsigdb` from newer versions of ``sbsigntool`` if it is available):

   .. code:: none

      sudo fwts uefidump - | grep Secure
      Name: [[SecureBoot]].
        Value: 0x01 (Secure Boot Mode On).


.. _efilinux-bootloader:

efilinux bootloader
~~~~~~~~~~~~~~~~~~~

.. important:: It is highly recommended to use the shim and GRUB2 instead of efilinux for the bootloader.

In theory, you should be able to do:

.. code:: none

  sudo apt-get install efilinux efilinux-signed
  sudo cp /usr/lib/efilinux/efilinux.efi /boot/efi/EFI/ubuntu
  sudo cp /boot/vmlinuz-3.5.0-19-generic.efi.signed /boot/efi/EFI/ubuntu/vmlinuz
  sudo cp /boot/initrd-3.5.0-19-generic /boot/efi/EFI/ubuntu/initrd
  sudo cp /usr/lib/efilinux-signed/efilinux.efi.signed /boot/efi/EFI/ubuntu/efilinux-signed.efi
  sudo sh -c 'cat > /boot/efi/EFI/ubuntu/efilinux.cfg << EOM
  # efilinux menu 1
  EFILINUX MENU
  Ubuntu EFILINUX
  0:\EFI\ubuntu\vmlinuz initrd=0:\EFI\ubuntu\initrd root=... ...
  EOM
  '

Then reboot, select one of :file:`efilinux.efi` or :file:`efilinux-signed.efi` from :guilabel:`Boot From File` and get a menu. Unfortunately, with current OVMF images, this does not work (though it apparently `works on USB installation images <https://wiki.ubuntu.com/USBStickUEFIHowto>`_).

The shim should try to boot anything named :file:`grubx64.efi`, so we can play a trick on the shim by naming :file:`efilinux.efi.signed` as :file:`grubx64.efi`:

#. Boot an OVMF virtual UEFI machine (see :ref:`vm-installation-and-preparation`).
#. Install required packages:

   .. code:: none

      sudo apt-get install sbsigntool openssl grub-efi-amd64-signed fwts shim-signed linux-signed-generic efilinux-signed

#. Install the signed bootloader (shim and GRUB2):

   .. code:: none

      sudo grub-install --uefi-secure-boot

#. Backup GRUB2:

   .. code:: none

      sudo cp /boot/efi/EFI/ubuntu/grubx64.efi /boot/efi/EFI/ubuntu/grubx64-orig.efi

#. Install the signed efilinux bootloader as :file:`grubx64.efi`:

   .. code:: none

      sudo cp /usr/lib/efilinux-signed/efilinux.efi.signed /boot/efi/EFI/ubuntu/efilinux-signed.efi
      sudo cp /usr/lib/efilinux-signed/efilinux.efi.signed /boot/efi/EFI/ubuntu/grubx64.efi
      sudo cp /boot/vmlinuz-3.5.0-19-generic.efi.signed /boot/efi/EFI/ubuntu/vmlinuz
      sudo cp /boot/initrd-3.5.0-19-generic /boot/efi/EFI/ubuntu/initrd
      sudo sh -c 'cat > /boot/efi/EFI/ubuntu/efilinux.cfg << EOM
      # efilinux menu 1
      EFILINUX MENU
      Ubuntu text boot
      0:\EFI\ubuntu\vmlinuz initrd=0:\EFI\ubuntu\initrd root=/dev/sda3
      Ubuntu graphical boot
      0:\EFI\ubuntu\vmlinuz initrd=0:\EFI\ubuntu\initrd root=/dev/sda3 quiet splash
      Ubuntu recovery
      0:\EFI\ubuntu\vmlinuz initrd=0:\EFI\ubuntu\initrd root=/dev/sda3 single
      EOM
      '

#. Reboot the VM and :guilabel:`Boot from File` as above, except choose :file:`shimx64.efi` instead of :file:`grubx64.efi`

   Unfortunately, this doesn't work either, and it seems to be a bug in the OVMF implementation. Copying :file:`efilinux-signed.efi` to :file:`/boot/efi/EFI/BOOT/BOOTX64.EFI` (and :file:`efilinux.cfg` in :file:`/boot/efi/EFI/BOOT`) also doesn't work. With the above configuration, you can boot efilinux via the EFI shell:

   .. code:: none

      Shell> fs0:\EFI\ubuntu\efilinux-signed.efi

   However, you can't setup Secure Boot using :command:`sb-setup` since it requires a reboot, and you aren't able to boot into the EFI shell with a warm reboot. And a cold reboot resets the Secure Boot configuration. It should be possible to enlist the keys manually by copying the DER files into :file:`/boot/efi` and manually enlist them via the EFI configuration (but even then, it is only good for that one boot).


.. _miscellaneous:

Miscellaneous
-------------


.. _disabling_secure_boot:

Disabling Secure Boot
~~~~~~~~~~~~~~~~~~~~~

If you already committed your changes to the keystore (which enrols PK and toggles Secure Boot to enabled) and want to disable Secure Boot, you can reboot and go into the :guilabel:`Device Manager/Secure Boot Configuration` in the EFI firmware configuration, then :guilabel:`Unenroll PK` (highlight :guilabel:`[ ]` and press :kbd:`Enter`). You can then delete the signatures in KEK, DB, and DBX. You should also be able to unenrol PPK and disable Secure Boot with:

.. code:: none

   /tmp/sb-setup reset


.. _disabling-secure-boot-validation-in-shim:

Disabling Secure Boot validation in shim
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

With the VM installed, you can start a terminal and run the following commands, which ask you to choose a password:

.. code:: none

   sudo mokutil --disable-validation

To enable validation again use:

.. code:: none

   sudo mokutil --enable-validation

Reboot, and you will be starting in MokManager, a blue screen with prompts that walks you through enabling or disabling validation. You need to type in some of the characters of the password again.


.. _resetting-the-keystore:

Resetting the keystore
~~~~~~~~~~~~~~~~~~~~~~

The keystore and key material are stored in :file:`/etc/secureboot`. If you have not committed your changes to the keystore, you can:

.. code:: none

   sudo rm -rf /etc/secureboot
   /tmp/sb-setup enroll ...

If you have committed your changes to the keystore, disable Secure Boot (see :ref:`disabling-secure-boot-validation-in-shim`) and empty all the key databases in firmware.

**Enabling Secure Boot after unenrolling PK**: if you unenrolled PK, you can re-enable it again with (uses existing keys):

.. code:: none

   /tmp/sb-setup enroll microsoft


.. _converting-a-der-formatted-certificate-to-pem:

Converting a DER formatted certificate to PEM
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

:command:`sbverify` takes a PEM formatted certificate. You can convert the Canonical master DER formatted certificate:

.. code:: none

   openssl x509 -inform DER -in ~/keys/canonical-master-public.der \
                  -outform PEM -out ~/keys/canonical-master-public.pem

and the Microsoft one:

.. code:: none

   openssl x509 -inform DER -in ~/keys/microsoft-uefica-public.der \
                  -outform PEM -out ~/keys/microsoft-uefica-public.pem


.. _creating-a-pem-certificate-chain-from-der-formatted-certificates:

Creating a PEM certificate chain from DER formatted certificates
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To create a PEM certificate chain suitable for use with :command:`sbverify`, you convert all the DER certificates to PEM, then concatenate them in one certificate. E.g., to create the Canonical certificate chain file:

.. code:: none

   openssl x509 -inform DER -in ~/keys/canonical-master-public.der \
                  -outform PEM -out ~/keys/canonical-master-public.pem
   openssl x509 -inform DER -in ~/keys/canonical-signing-public.der \
                  -outform PEM -out ~/keys/canonical-signing-public.pem
   cat ~/keys/canonical-master-public.pem ~/keys/canonical-signing-public.pem \
         > ~/keys/canonical-master-signing-public-chain.pem


.. _verifying-the-signature-on-a-signed-pe-coff-or-signed-kernel-image:

Verifying the signature on a signed PE/COFF or signed kernel image
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To verify Microsoft's signature on the signed shim bootloader (must first create the PEM certificate, above):

.. code:: none

   sbverify --cert ~/keys/microsoft-uefica-public.pem
   /boot/efi/EFI/ubuntu/shimx64.efi Signature verification OK

To verify Canonical's signature on the signed grub bootloader (must first create the PEM certificate, above):

.. code:: none

   sbverify --cert ~/keys/canonical-master-public.pem
   /boot/efi/EFI/ubuntu/grubx64.efi Signature verification OK

To verify Ubuntu signature on the signed kernel, you must first extract the signature from the kernel image, then use :pkg:`sbverify` to verify the image with the detached signature (must first create the PEM certificate chain, above):

.. code:: none

   sbattach --detach /tmp/vmlinuz-3.5.0-27-generic.efi.signature \
   /boot/vmlinuz-3.5.0-27-generic.efi.signed

   sbverify --cert ~/keys/canonical-master-signing-public-chain.pem \
            --detached /tmp/vmlinuz-3.5.0-27-generic.efi.signature \
            /boot/vmlinuz-3.5.0-27-generic.efi.signed

   Signature verification OK


.. _updating-key-databases:

Updating key databases
----------------------


.. _inserting-keys-in-shim-s-keyring:

Inserting keys in shim's keyring
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To insert your own keys in the shim keyring, use:

.. code:: none

   sudo mokutil --import <path to cert in DER format>


.. _removing-an-enrolled-key-from-shim-s-keyring:

Removing an enrolled key from shim's keyring
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You can remove certificates from the shim keyring if you still have access to the DER-format certificate by using:

.. code:: none

   sudo mokutil --delete <path to DER cert>

If you don't have access to the certificate, another option is to completely reset the shim keyring:

.. code:: none

   sudo mokutil --reset


.. _certificates:

Certificates
~~~~~~~~~~~~

To create an entry for a key database:

#. Create a signature list variable with the thing you want to blocklist using :command:`sbsiglist`.
#. Sign the signature list variable with a key pair that is in KEK or PK using :command:`sbvarsign`.
#. Add the signed update to a keystore.
#. Use :command:`sbkeysync` to add the signed update to the key database.

For example, if using the user key generated above, you can add a signed update to the blocklist database (dbx) for the Microsoft Corporation UEFI CA:

.. code:: none

   guid=$(uuidgen)
   sbsiglist --owner $guid --type x509 \
             --output microsoft_uefica_dbx-test.siglist \
             ~/keys/microsoft-uefica-public.der
   sbvarsign --key /etc/secureboot/key-material/test-key.rsa \
             --cert /etc/secureboot/key-material/test-cert.pem \
             --output microsoft_uefica_dbx-test.siglist.signed \
             dbx \
             microsoft_uefica_dbx-test.siglist

   ls -1
   microsoft_uefica_dbx-test.siglist
   microsoft_uefica_dbx-test.siglist.signed

   sudo cp microsoft_uefica_dbx-test.siglist.signed /etc/secureboot/keys/dbx
   sudo sbkeysync --verbose

If you have the :pkg:`secureboot-db` package installed, you can copy to the system wide updates keystore:

.. code:: none

   sudo cp microsoft_uefica_dbx-test.siglist.signed /usr/share/secureboot/updates/dbx
   sudo dpkg-reconfigure secureboot-db
   Filesystem keystore:
     /usr/share/secureboot/updates/dbx/microsoft_uefica_dbx-test.siglist.signed [2907 bytes]
   firmware keys:
     PK:
       /CN=test-key
     KEK:
       /C=US/ST=Washington/L=Redmond/O=Microsoft Corporation/CN=Microsoft Corporation KEK CA 2011
       /CN=test-key
     db:
       /C=US/ST=Washington/L=Redmond/O=Microsoft Corporation/CN=Microsoft Corporation UEFI CA 2011
       /C=US/ST=Washington/L=Redmond/O=Microsoft Corporation/CN=Microsoft Windows Production PCA 2011
     dbx:
   filesystem keys:
     PK:
     KEK:
     db:
     dbx:
       /C=US/ST=Washington/L=Redmond/O=Microsoft Corporation/CN=Microsoft Corporation UEFI CA 2011
        from /usr/share/secureboot/updates/dbx/microsoft_uefica_dbx-test.siglist.signed
   New keys in filesystem:
    /usr/share/secureboot/updates/dbx/microsoft_uefica_dbx-test.siglist.signed
   Inserting key update /usr/share/secureboot/updates/dbx/microsoft_uefica_dbx-test.siglist.signed into dbx


.. _sha256-hashes:

sha256 hashes
~~~~~~~~~~~~~

**FIXME**

**TODO (needs :pkg:`sbtools` support)**: Ultimately, this should be in ``sbsign`` since the hash of PE/COFF image is the hash of everything except the embedded signature. We'd like to do something like this, but it doesn't work because it doesn't exclude the embedded signature (and if it wasn't signed, there is no point blocklisting it):

.. code:: none

   echo -n "0x`sha256sum grubx64.efi | cut -d ' ' -f 1`" |
             | xxd -r -g 1 -c 64 > /tmp/sha256.bin

Then we would create a signed update with:

.. code:: none

   sbsiglist --owner $guid --type sha256 \
             --output /tmp/sha256.bin.siglist \
             /tmp/sha256.bin
   sbvarsign --key /etc/secureboot/key-material/test-key.rsa \
             --cert /etc/secureboot/key-material/test-cert.pem \
             --output /tmp/sha256.bin.siglist.signed \
             dbx \
             /tmp/sha256.bin.siglist


.. _testing-signed-updates-via-secureboot-db:

Testing signed updates via :pkg:`secureboot-db`
-----------------------------------------------

Updates to ``db`` and ``dbx`` need to be performed as keys are rotated and things are blocklisted. This will be handled by the :pkg:`secureboot-db` package. In essence, :pkg:`secureboot-db` ships a keystore in :file:`/usr/share/secureboot/updates` for updating ``db`` and ``dbx``, and then in package ``postinst`` run:

.. code:: none

   keystore=/usr/share/secureboot/updates \
   sbkeysync --no-default-keystores --keystore "$keystore" --verbose

:command:`sbkeysync` only adds new updates, so the management of :pkg:`secureboot-db` is simple and updates primarily consist of adding the signed updates to the keystore. See :file:`debian/README.source` and :file:`debian/README.Debian` for details.

.. note::

   - Improperly updating :pkg:`secureboot-db` could result in all systems with Secure Boot enabled failing to boot.

   - When Secure Boot is enabled, updates to DB and DBX must be signed by something that verifies via the chain of trust to something in KEK. As a result, when testing :pkg:`secureboot-db`, expect :command:`sbkeysign` to complain when adding a signed update from Microsoft on a machine that does not have the Microsoft key in KEK but does have Secure Boot enabled.

   - :command:`sbkeysync` (and therefore :pkg:`secureboot-db`) add the updates to DB and DBX unconditionally when Secure Boot is disabled


.. _test-cases:

Test cases
----------


.. _functional-tests:

Functional tests
~~~~~~~~~~~~~~~~

- Booting with Secure Boot disabled

  - for each of GRUB2-signed only and shim-signed

    - install bootloader
    - reboot and verify the machine boots with Secure Boot disabled

- Booting with Secure Boot enabled

  - for each of :pkg:`linux-generic` (unsigned) and :pkg:`linux-signed-generic`

    - for each of Microsoft/shim-signed, Canonical/GRUB2-signed and user signed

      * verify vendor's (or when test user keys, user's) keys are in KEK and DB and Secure Boot is enabled
      * reboot and verify the machine still boots
      * install updated :pkg:`secureboot-db`, verifying:

        * package installation succeeded
        * :pkg:`secureboot-db` properly used 'Breaks' and pulled in necessary packages
        * the updates were added to firmware (check EFI configuration, as well as output from :command:`sbkeysync`)
        * reboot and verify the machine still boots


.. _verification-tests:

Verification tests
~~~~~~~~~~~~~~~~~~

With Secure Boot enabled with the shim and using Microsoft keys.

Shim validation
^^^^^^^^^^^^^^^

Tests firmware properly verifies our signed shim.

Add a dbx entry for an old shim and try booting (should fail):
  TODO

Add a dbx entry for the 'Microsoft Corporation UEFI CA' and try booting (should fail):
  .. code:: none

    guid=$(uuidgen) $ sbsiglist --owner $guid --type x509 \
          --output microsoft_uefica_dbx-test.siglist \
          ~/keys/microsoft-uefica-public.der

    sbvarsign --key /etc/secureboot/key-material/test-key.rsa \
              --cert /etc/secureboot/key-material/test-cert.pem \
              --output microsoft_uefica_dbx-test.siglist.signed \
              dbx \
              microsoft_uefica_dbx-test.siglist

    sudo cp microsoft_uefica_dbx-test.siglist.signed /etc/secureboot/keys/dbx
    sudo sbkeysync --verbose

  Now try to :guilabel:`Boot from File` :file:`shimx64.efi` (succeed if Secure Boot is disabled, fail if enabled). To reset back to a working signed GRUB2, delete the signature from the DBX database in firmware, and then on reboot:

  .. code:: none

    sudo rm -f /etc/secureboot/keys/dbx/*signed

Replace shim with unsigned shim (should fail):
  .. code:: none

    sudo apt-get install shim
    sudo cp /usr/lib/shim/shim.efi /boot/efi/EFI/ubuntu/

  Now try to :guilabel:`Boot from File` :file:`shim.efi` (succeed if Secure Boot is disabled, fail if enabled).

Replace shim with signed shim using a key not in DB (should fail):
  .. code:: none

     sudo apt-get install shim
     sudo sbsign --key /etc/secureboot/key-material/test-key.rsa \
                 --cert /etc/secureboot/key-material/test-cert.pem \
                 --output /boot/efi/EFI/ubuntu/shim_user-signed.efi \
                 /usr/lib/shim/shim.efi

  Now try to :guilabel:`Boot from File` :file:`shimx64.efi` (succeed if Secure Boot is disabled, fail if enabled).

OPTIONAL: replace signed shim with a bit-flipped/fuzzed shim (should fail).
  |nbsp|


GRUB2 validation
^^^^^^^^^^^^^^^^

Tests shim properly verifies our bootloader.

Try to boot GRUB2 directly, without shim (should fail).
  |nbsp|

Add a dbx entry for an old GRUB2 and try booting (should fail):
  TODO

Add a dbx entry for the 'Canonical Ltd. Master Certificate Authority' and try booting (should fail):
  .. code:: none

     guid=$(uuidgen)
     sbsiglist --owner $guid --type x509 \
               --output canonical_ca_dbx-test.siglist \
               ~/keys/canonical-master-public.der

     sbvarsign --key /etc/secureboot/key-material/test-key.rsa \
               --cert /etc/secureboot/key-material/test-cert.pem \
               --output canonical_ca_dbx-test.siglist.signed \
               dbx \
               canonical_ca_dbx-test.siglist

     sudo cp canonical_ca_dbx-test.siglist.signed /etc/secureboot/keys/dbx
     sudo sbkeysync --verbose

  Now try to :guilabel:`Boot from File` :file:`shim_user-signed.efi` (succeed if Secure Boot is disabled, fail if enabled). To reset back to a working signed GRUB2, delete the signature from the DBX database in firmware and then on reboot:

  .. code:: none

     sudo rm -f /etc/secureboot/keys/dbx/*signed

Add a dbx entry for the 'Canonical Ltd. Secure Boot Signing' key and try booting (should fail):
  .. code:: none

     guid=$(uuidgen)
     sbsiglist --owner $guid --type x509 \
               --output canonical_signing_dbx-test.siglist \
               ~/keys/canonical-signing-public.der

     sbvarsign --key /etc/secureboot/key-material/test-key.rsa \
               --cert /etc/secureboot/key-material/test-cert.pem \
               --output canonical_signing_dbx-test.siglist.signed \
               dbx \
               canonical_signing_dbx-test.siglist

     sudo cp canonical_signing_dbx-test.siglist.signed /etc/secureboot/keys/dbx
     sudo sbkeysync --verbose

  Now try to :guilabel:`Boot from File` :file:`shimx64.efi` (succeed if Secure Boot is disabled, fail if enabled). To reset back to a working signed GRUB2, delete the signature from the DBX database in firmware, and then on reboot:

  .. code:: none

     sudo rm -f /etc/secureboot/keys/dbx/*signed

Replace GRUB2 with unsigned GRUB2 (should fail):
  .. code:: none

     sudo grub-install --no-uefi-secure-boot

  Now try to :guilabel:`Boot from File` :file:`shimx64.efi` (succeed if Secure Boot is disabled, fail if enabled). Run the following to reset to working signed GRUB2:

  .. code:: none

     sudo grub-install --uefi-secure-boot


Replace GRUB2 with signed GRUB2 using a key not in DB (should fail):
  .. code:: none

     sudo grub-install --uefi-secure-boot
     sudo sbsign --key /etc/secureboot/key-material/test-key.rsa \
                 --cert /etc/secureboot/key-material/test-cert.pem \
                 --output /boot/efi/EFI/ubuntu/grubx64.efi \
                 /usr/lib/grub/x86_64-efi-signed/grubx64.efi.signed

  Now try to :guilabel:`Boot from File` :file:`shimx64.efi` (succeed if Secure Boot is disabled, fail if enabled). Run the following to reset to working signed GRUB2:

  .. code:: none

     sudo grub-install --uefi-secure-boot

OPTIONAL: replace signed GRUB2 with a bit-flipped/fuzzed GRUB2 (should fail).
  |nbsp|


Kernel
^^^^^^

Tests GRUB2 verification of kernel and fallback mechanism.

Add a dbx entry for an old kernel and try booting (should fail):
  TODO

Replace kernel with unsigned kernel (should succeed):
  .. code:: none

     sudo apt-get remove --purge linux-signed\*

  Now try to :guilabel:`Boot from File` :file:`shimx64.efi` (succeed if Secure Boot is disabled, fail if enabled). Run the following to reset to working signed kernel:

  .. code:: none

     sudo apt-get install linux-signed-generic

Replace kernel with signed kernel using a key not in DB (should succeed):
  .. code:: none

     sudo cp /boot/vmlinuz--generic.efi.signed \
             /boot/vmlinuz--generic.efi.signed.bak

     sudo sbsign --key /etc/secureboot/key-material/test-key.rsa \
                 --cert /etc/secureboot/key-material/test-cert.pem \
                 --output /boot/vmlinuz-generic.efi.signed \
                          /boot/vmlinuz-generic.efi.signed.bak

  Now try to :guilabel:`Boot from File` :file:`shimx64.efi` (succeed if Secure Boot is disabled, fail if enabled). Run the following to reset to working signed GRUB2:

  .. code:: none

     sudo apt-get remove --purge linux-signed*
     sudo apt-get install linux-signed-generic

OPTIONAL: replace signed kernel with a bit-flipped/fuzzed kernel (should fail).
  |nbsp|
