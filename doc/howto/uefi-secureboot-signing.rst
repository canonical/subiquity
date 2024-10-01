.. _how-to-sign-your-own-uefi-binaries-for-secure-boot:

How to sign your own UEFI binaries for Secure Boot
==================================================

.. This content is from:
.. https://wiki.ubuntu.com/UEFI/SecureBoot/Signing

.. important:: This article is for development purposes and a WIP. Don't use unless you know you're doing!

There are two options:

- Using Ubuntu directly with :command:`sbsign` and :command:`kmodsign`.
- Using the "real" method used by Microsoft to sign binaries with a Windows-only application.

For more details on signing binaries, see `Image Signing <https://wiki.ubuntu.com/UEFI/SecureBoot/KeyManagement/ImageSigning>`_.


:command:`sbsign` and :command:`kmodsign`
-----------------------------------------

:command:`sbsign` allows you to sign your own custom binaries (i.e. the files that would be loaded directly by firmware, be it a bootloader or a kernel).

To sign a binary using :command:`sbsign`, you need both the private and public part of a certificate in PEM format (see `Key Generation <https://wiki.ubuntu.com/UEFI/SecureBoot/KeyManagement/KeyGeneration>`_). The source file will not be modified:

.. code:: none

   sbsign --cert path/to/cert.crt --key path/to/cert.key \
          --output path/to/outputfile efi_binary

To validate a signature, you still need the public part of the signing certificate in PEM form:

.. code:: none

   sbverify --cert path/to/cert.crt efi_binary

:command:`kmodsign` is used exclusively to sign kernel modules. It also requires the signing certificates to be in a different format than for :command:`sbsigntool`; for :command:`kmodsign`, the certificates need to be in the DER format. Conveniently, if you need to use DKMS modules, an appropriate certificate may already exist in :file:`/var/lib/shim-signed/mok`.

To sign a custom module (in this example, the generated MOK is already available on a system):

.. code:: none

   kmodsign sha512 \
      /var/lib/shim-signed/mok/MOK.priv \
      /var/lib/shim-signed/mok/MOK.der \
      module.ko


Using :command:`signfootl.exe` from Microsoft
---------------------------------------------

.. note:: This requires access to a system running Windows.

Download :command:`signtool.exe` from Microsoft (it is a single binary), and run it. Refer to :command:`signtool /?` for help.
