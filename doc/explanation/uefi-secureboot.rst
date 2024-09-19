.. _uefi-secure-boot:

UEFI Secure Boot
================

.. This content is from:
.. https://wiki.ubuntu.com/UEFI/SecureBoot

.. important:: This article is for development purposes and a WIP. Don't use unless you know you're doing!

UEFI (Unified Extensible Firmware Interface) Secure Boot is a verification mechanism for ensuring that code launched by firmware is trusted.

In brief, Secure Boot works by placing the root of trust in firmware. While other implementations are possible, in practice, the chain of trust is achieved via x509 certificates. A root CA (Certificate Authority) is embedded in firmware such that it can then validate the signed bootloader. The signed bootloader can then validate the signed kernel or signed second-stage boot loader, and so on.

Proper, secure use of UEFI Secure Boot requires that each binary loaded at boot is validated against known keys, located in firmware, that denote trusted vendors and sources for the binaries, or trusted specific binaries that can be identified via cryptographic hashing.

Most x86 hardware comes from the factory pre-loaded with Microsoft keys. This means we can generally rely on the firmware on these systems to trust binaries that are signed by Microsoft, and the Linux community relies on this assumption for Secure Boot to work. This is the same process used by distributions from, for example, Red Hat and SUSE.

Many ARM and other architectures also support UEFI Secure Boot but may not be pre-loading keys in firmware. On these architectures, it may be necessary to re-sign boot images with a certificate that is loaded in firmware by the owner of the hardware.


.. _key-databases:

Key databases
-------------

Various key databases are used to provide flexibility and maintain strong security:

DB ('signature database')
  Contains the trusted keys used for authenticating any applications or drivers executed in the UEFI environment.

DBX ('forbidden signature database' or 'signature database blocklist')
  Contains a set of explicitly untrusted keys and binary hashes. Any application or driver signed by these keys or matching these hashes is blocked from execution.

KEK ('key exchange keys' database)
  Contains the set of keys trusted for updating DB and DBX

PK ('platform key')
  While PK is often referred to simply as a single public key, it could be implemented as a database). Only updates signed with PK can update the KEK database.

The suggested implementation by UEFI:

- OEM (Original Equipment Manufacturer) key in PK.
- OS vendor keys in KEK and DB. OEM may also have a key in KEK and DB.

Systems shipping with Windows 8 typically use the following:

- OEM key in PK
- 'Microsoft Corporation KEK CA' key in KEK
- 'Microsoft Windows Production PCA' and 'Microsoft Corporation UEFI CA' keys in DB (note, the 'Microsoft Corporation UEFI CA' is not guaranteed to be present in DB -- while recommended, this is EFI firmware vendor/OEM dependent)


.. _how-uefi-secure-boot-works-on-ubuntu:

How UEFI Secure Boot works on Ubuntu
------------------------------------

On Ubuntu, all pre-built binaries intended to be loaded as part of the boot process, with the exception of the ``initrd`` image, are signed by Canonical's UEFI certificate, which itself is implicitly trusted by being embedded in the shim loader, itself signed by Microsoft.

On architectures or systems where pre-loaded signing certificates from Microsoft are not available or loaded in firmware, users may replace the existing signatures on shim or grub and load them as they wish, verifying against their own certificates imported in the system's firmware.

As the system boots, firmware loads the shim binary as specified in firmware boot entry variables. Ubuntu installs its own boot entry at installation time and may update it any time the GRUB bootloader is updated. Since the shim binary is signed by Microsoft; it is validated and accepted by the firmware when verifying against certificates already present in firmware. As the shim binary embeds a Canonical certificate as well as its own trust database, further elements of the boot environment can, in addition to being signed by one of the acceptable certificates pre-loaded in firmware, be signed by Canonical's UEFI key.

The next thing loaded by the shim is the second-stage image. This can be one of two things:

- GRUB -- if the system is booting normally
- MokManager -- if key management is required, as configured by firmware variables (usually changed when the system was previously running)


Booting normally
~~~~~~~~~~~~~~~~

If booting normally, the GRUB binary (:file:`grub*.efi`) is loaded and its validation is attempted against all previously-known trusted sources. The GRUB binary for Ubuntu is signed by the Canonical UEFI key, so it is successfully validated, and the boot process continues.


Booting to perform key-management
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If booting to proceed with key management tasks, the MokManager binary (:file:`mm*.efi`) is loaded. This binary is explicitly trusted by the shim by being signed by an ephemeral key that only exists while the shim binary is being built. This means only the MokManager binary built with a particular shim binary is allowed to run, and it limits the possibility of a compromise from the use of compromised tools.

MokManager allows any user present at the system console to enrol keys, remove trusted keys, enrol binary hashes and toggle Secure Boot validation at the shim level, but most tasks require a previously set password to be entered to confirm that the user at the console is indeed the person who requested changes. Such passwords only survive across a single run of the shim or MokManager. The passwords are cleared as soon as the process is completed or cancelled. Once key management is completed, the system is rebooted and does not simply continue with booting because the key management changes may be required to successfully complete the boot.


GRUB process
~~~~~~~~~~~~

Once the system continues booting to GRUB, the GRUB process loads any required configuration (usually loading configuration from the ESP (EFI System Partition) pointing to another configuration file on the root or boot partition), which points it to the kernel image to load.

As EFI applications up to this point have full access to the system firmware, including access to changing trusted firmware variables, the kernel to load must also be validated against the trust database. Official Ubuntu kernels are signed by the Canonical UEFI key, so they are successfully validated, and control is handed over to the kernel. ``initrd`` images are not validated.


Booting unofficial kernels
~~~~~~~~~~~~~~~~~~~~~~~~~~

In the case of unofficial kernels, or kernels built by users, additional steps need to be taken if users wish to load such kernels while retaining the full capabilities of UEFI Secure Boot. All kernels must be signed to be allowed to load by GRUB when UEFI Secure Boot is enabled, so the user is required to proceed with :ref:`their own signing <how-to-sign-your-own-uefi-binaries-for-secure-boot>`.

Alternatively, users can:

- Disable validation in the shim while booting with Secure Boot enabled on an official kernel:

   .. code:: none

      sudo mokutil --disable-validation

   Provide a password when prompted and reboot.

- Disable Secure Boot in the firmware altogether.

Up to this point, any failure to validate an image to load is met with a critical error, which stops the boot process. The system does not continue booting and may automatically reboot after a period of time given that other Boot Entry variables may contain boot paths that are valid and trusted.

Once loaded, validated kernels disable the Boot Services of the firmware, thus dropping privileges and effectively switching to user mode where access to trusted variables is limited to read-only.

Given the broad permissions afforded to kernel modules, any module not built into the kernel also needs to be validated upon loading. Modules built and shipped by Canonical with the official kernels are signed by the Canonical UEFI key and as such are trusted.

Custom-built modules require the user to take the necessary steps to sign the modules before loading them is allowed by the kernel. This can be achieved by using the :command:`kmodsign` command (refer to :ref:`how-to-sign-your-own-uefi-binaries-for-secure-boot`). Given that many users require third-party modules for their systems to work properly or for some devices to function, and that these third-party modules require building locally on the system to be fitted to the running kernel, Ubuntu provides tooling to automate and simplify the signing process.

Unsigned modules are refused by the kernel. Any attempt to insert them with :command:`insmod` or :command:`modprobe` fails with an error message.


Enrolling a PPA signing key
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Providers, including, for example, the Canonical Kernel team (`~~canonical-kernel-team <https://launchpad.net/~canonical-kernel-team/+archive/ubuntu/ppa>`_), use PPA (Personal Package Archive) repositories on Launchpad to offer custom kernels with one-off fixes or for testing purposes.

.. important:: Only enrol keys from trusted providers (PPA owners). Adding a signing key allows trusting any UEFI binary built and signed from a given PPA.

#. Download the :file:`signed.tar.gz` file from the PPA:

   #. ``http://ppa.launchpad.net/<user>/<ppa name>/ubuntu``
   #. Under ``dists/<codename>/signed``
   #. The right name for the product, such as ``linux-amd64``.

#. Verify the file integrity using the provided :file:`SHA256SUMS` file.
#. Extract the contents of the file.
#. Go to the :file:`<version>/control` directory.
#. Convert the certificate from the PEM format to the DER format.
#. Enrol the :file:`uefi.crt` certificate.


Enrolling a signing key from a third-party archive
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Ask for the public certificate from the publisher of the package.


.. _ubuntu-chain-of-trust:

Ubuntu chain of trust
---------------------

In order to boot on the widest range of systems, Ubuntu uses the following chain of trust:

#. Microsoft signs Canonical's shim 1st-stage bootloader with their 'Microsoft Corporation UEFI CA'. When the system boots and Secure Boot is enabled, the firmware verifies that this 1st-stage bootloader (from the :pkg:`shim-signed` package) is signed with a key in DB (in this case 'Microsoft Corporation UEFI CA').

#. The second-stage bootloader (:pkg:`grub-efi-amd64-signed`) is signed with Canonical's 'Canonical Ltd. Secure Boot Signing' key. The shim 1st-stage bootloader verifies that the second-stage GRUB2 bootloader is properly signed.

#. The second-stage GRUB2 bootloader boots an Ubuntu kernel (as of 2012/11, if the kernel (:pkg:`linux-signed`) is signed with the 'Canonical Ltd. Secure Boot Signing' key, then GRUB2 boots the kernel, which in turn applies quirks and calls ``ExitBootServices``. If the kernel is unsigned, GRUB2 calls ``ExitBootServices`` before booting the unsigned kernel).

#. If signed kernel modules are supported, the signed kernel verifies them during kernel boot.

As the above gives the ability to control boot to the OEM and Microsoft, users may want to:

- Install their own key in PK, KEK, and DB, then re-sign GRUB2 and use it without a shim (and optionally sign the kernel with their own key).

- Install their own key in PK and KEK:

  - 'Canonical Ltd. Master Certificate Authority' key in KEK and DB
  - Microsoft keys in KEK (for updates to DBX)

  This gives some control of boot to Canonical but allows for the :pkg:`grub-efi-amd64-signed` and :pkg:`linux-signed` packages and any DB/DBX updates from Microsoft and Canonical to work without re-signing.

- Install their own key in the shim's own keyring when testing only Canonical or user-signed GRUB2 or kernel and modules.

When testing, a minimum shim boot, Canonical-signed GRUB2 boot, and user-signed GRUB2 boot should be covered.

.. important::

    Canonical's Secure Boot implementation in Ubuntu is primarily about hardware enablement, and this page focuses on how to test Secure Boot for common hardware-enablement configurations. The intent is not on enabling Secure Boot to harden your system. To use Secure Boot as a security mechanism, an appropriate solution is to use your own keys (optionally enrolling additional keys, see above) and update the bootloader to prohibit booting an unsigned kernel. Starting with Ubuntu 16.04 LTS, the system supports enforcing secure boot.

Initial implementation plan: `Implementation Plan <https://lists.ubuntu.com/archives/ubuntu-devel/2012-June/035445.html>`_.


.. _supported-architectures:

Supported architectures
-----------------------

-  **amd64**: A shim binary signed by Microsoft and a GRUB binary signed by Canonical are provided in the Ubuntu main archive as :pkg:`shim-signed` or :pkg:`grub-efi-amd64-signed`.

-  **arm64**: As of 20.04 ('focal'), a shim binary signed by Microsoft and a GRUB binary signed by Canonical are provided in the Ubuntu main archive as :pkg:`shim-signed` or :pkg:`grub-efi-arm64-signed`.


.. _testing-uefi-secure-boot:

Testing UEFI Secure Boot
------------------------

For guidance on testing Secure Boot on your system, consult :ref:`testing-secure-boot`.


.. _how-can-i-do-non-automated-signing-of-drivers:

How can I do non-automated signing of drivers?
----------------------------------------------

Some projects require the use of custom kernel drivers that are not set up to work with DKMS. In these cases, use the tools included in the :pkg:`shim-signed` package: the :command:`update-secureboot-policy` script is available to generate a new MOK (Machine-Owner Key) (if no DKMS-built modules have triggered generating one already).

Use the following command to enrol an existing key into the shim:

.. code:: none

   sudo update-secureboot-policy --enrol-key

If no MOK exists, the script exits with a message to that effect. If the key is already enrolled, the script exits, doing nothing. If the key exists but is not shown to be enrolled, the user is prompted for a password to use after reboot, so that the key can be enrolled.

To generate a new MOK, use:

.. code:: none

   sudo update-secureboot-policy --new-key

And then enrol the newly-generated key into the shim with the previously-mentioned command.

Kernel modules can then be signed with the :command:`kmodsign` command (see :ref:`how-to-sign-your-own-uefi-binaries-for-secure-boot`) as part of their build process.


.. _security-implications-in-machine-owner-key-management:

Security implications in Machine-Owner Key management
-----------------------------------------------------

The MOK generated at installation time or on upgrade is machine-specific and only allowed by the kernel or the shim to sign kernel modules by the use of a specific OID (Object Identifier) (1.3.6.1.4.1.2312.16.1.2) denoting the limitations of the MOK.

Recent shim versions include logic to follow the limitations of module-signing-only keys. These keys are allowed to be enrolled in the firmware in the shim trust database but are ignored when the shim or GRUB validate images to load in the firmware.

The shim ``verify()`` function only successfully validates images signed by keys that do not include the "Module-signing only" (1.3.6.1.4.1.2312.16.1.2) OID. The Ubuntu kernels use the global trust database (which includes both shim and firmware OIDs) and accept any of the included keys as signing keys when loading kernel modules.

Given the limitations imposed on the automatically generated MOK and the fact that users with superuser access to the system and access to the system console to enter the password required when enrolling keys already have high-level access to the system, the generated MOK key is kept on the file system as regular files owned by root with read-only permissions.

This is deemed sufficient to limit access to the MOK for signing by malicious users or scripts, especially given that no MOK exists on the system unless it requires third-party drivers. This limits the possibility of a compromise from the misuse of a generated MOK key to signing a malicious kernel module. This is equivalent to a compromise of userland applications, which would already be possible with superuser access to the system, and securing this is out of the scope of UEFI Secure Boot.

Previous systems may have had Secure Boot validation disabled in the shim. As part of the upgrade process, these systems will be migrated to re-enabling Secure Boot validation in the shim and enrolling a new MOK key when applicable.


.. _mok-generation-and-signing-process:

MOK generation and signing process
----------------------------------

The key generation and signing process is slightly different based on whether dealing with a brand new installation or an upgrade of a system previously running Ubuntu. These two cases are clearly marked below.

In all cases, if the system is not booting in UEFI mode, no special kernel-module signing steps or key generation happen.

If Secure Boot is disabled, MOK generation and enrolment still happens, as the user may later enable Secure Boot. The system should work properly if that is the case.


.. _installing-ubuntu-on-a-new-system:

Installing Ubuntu on a new system
---------------------------------

The user steps through the installer. Early on, when preparing to install and only if the system requires third-party modules to work, the user is prompted for a system password that is clearly marked as being required after the installation is complete. While the system is being installed, a new MOK is automatically generated without further user interaction.

Third-party drivers or kernel modules required by the system are automatically built when the package is installed, and the build process includes a signing step. The signing step automatically uses the MOK generated earlier to sign the module, such that it can be immediately loaded once the system is rebooted and the MOK is included in the system trust database.

Once the installation is complete and the system is restarted, the user is presented with the MokManager program on the first boot (part of the installed shim loader). MokManager is a set of text-mode panels that allow the user to enrol the generated MOK. The user selects :guilabel:`Enrol MOK`, is shown a fingerprint of the certificate to enrol, and is prompted to confirm the enrolment. Once confirmed, the new MOK is entered in the firmware, and the user is asked to reboot the system.

When the system reboots, third-party drivers signed by the MOK just enrolled are loaded as necessary.


.. _release-upgrade-of-uefi-enabled-ubuntu-system-with-third-party-drivers:

Release upgrade of UEFI-enabled Ubuntu system with third-party drivers
----------------------------------------------------------------------

On upgrade, the :pkg:`shim` and :pkg:`shim-signed` packages are upgraded. The post-install tasks of the :pkg:`shim-signed` package proceed to generate a new MOK and prompt the user for a password that is clearly mentioned as being required once the upgrade process is completed and the system rebooted.

During the upgrade, the kernel packages and third-party modules are upgraded. Third-party modules are rebuilt for the new kernels, and their post-build process automatically signs them with the MOK.

After upgrade, it is recommended to reboot the system.

On reboot, the user is presented with the MokManager program (part of the installed shim loader). MokManager is a set of text-mode panels that allow the user to enrol the generated MOK. The user selects :guilabel:`Enrol MOK`, is shown a fingerprint of the certificate to enrol, and is prompted to confirm the enrolment.

The user is also presented with a prompt to re-enable Secure Boot validation (in case it was found to be disabled), and MokManager again requires confirmation from the user. Once all steps are confirmed, shim validation is re-enabled, the new MOK is entered in the firmware, and the user is asked to reboot the system.

When the system reboots, third-party drivers signed by the MOK just enrolled are loaded as necessary.

In all cases, once the system is running with UEFI Secure Boot enabled and a recent version of the shim, the installation of any new DKMS module (third-party driver) signs the built module with the MOK. This happens without user interaction if a valid MOK key exists on the system and appears to already be enrolled.

If no MOK exists or the existing MOK is not enrolled, a new key is automatically created just before signing and the user is prompted to enrol the key by providing a password, which is required upon reboot.
