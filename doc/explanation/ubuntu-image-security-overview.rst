.. _ubuntu-image-security-overview:

ubuntu-image security overview
==============================

Overview of security aspects of ubuntu-image.


Privileged execution
--------------------
 
``ubuntu-image`` requires **elevated permissions** to properly run. It is recommended to use a dedicated building machine. Make sure ``ubuntu-image`` is installed from a trusted source, and the provided configuration is trusted. 


Cryptography
------------

``ubuntu-image`` is a wrapper around several lower level tools to build an Ubuntu image. Therefore, the use of cryptographic technologies can be divided into two categories:

* Direct use in the ``ubuntu-image`` tool
* Indirect use in one of the wrapped tools


Cryptography in ubuntu-image itself and Go libraries
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Tarball SHA256 checksum: When building a ``classic`` image, user can provide a tarball serving as the rootfs content of the image. The SHA256 checksum of the tarball can optionally be provided to verify it has not been altered. This verification uses the `crypto/sha256`_ Go standard library package, which implements the SHA256 hash algorithm as defined in FIPS 180-4.

* Disk UUIDs: To generate unique disk IDs, ``ubuntu-image`` uses the ``Read()`` function from the `crypto/rand`_ Go standard library package, which implements a cryptographically secure random number generator.

* Model assertion signature: When building a ``snap`` image, the user must provide a signed model assertion. Verification of this signature is handled by the `snapd library`_,  which relies on SHA3-384 and SHA512 for hashing and on OpenPGP v4 signatures with RSA 4096/8192 keys.


Cryptography in wrapped tools
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* PPA handling: During the build, PPAs (Personal Package Archives) can be added to the ``apt`` configuration of the image. The fingerprint of the PPA can be declared in the configuration provided to ``ubuntu-image``. This value is passed to ``gpg`` to fetch the keys to validate the package signatures. The correct handling of these keys is delegated to ``gpg`` up to the point where ``ubuntu-image`` writes them to the resulting ``apt`` configuration.

* Downloaded resources: During the build, various resources are fetched from remote sources (seeds, packages, gadget trees). ``ubuntu-image`` is not enforcing the use of encrypted communication channels, but if they are used (HTTPS, Git over SSH, etc.), their correct handling is delegated to the tool actually pulling the resource (Germinate, Git, etc.). In this case, if any security-related error is causing a tool to fail, ``ubuntu-image`` also fails and displays the error, so the user is alerted and can take appropriate measures to remedy the problem.


Miscellaneous
~~~~~~~~~~~~~

* Secrets (passwords and hashes) can be present in the configuration files (image definition YAML) provided to ``ubuntu-image`` to build images. Specifically:

  * In the ``extra-ppas`` customisation section, authentication tokens ``user:password`` can be defined to access private PPAs. These values are used to write the ``apt`` configuration without any treatment.
  * In the ``manual`` customisation section, user accounts can be defined with plain text or hashed passwords. These values are directly passed to the ``chpassword`` utility without any treatment.
  * In the ``cloud-init`` customisation section, the given cloud-init configuration can contain hashed passwords. These values are written into `cloud-init`_ configuration files without any treatment.

  These configuration files should then be securely stored, and if secrets are used, they should ideally be injected at runtime.


.. LINKS

.. _crypto/rand: https://pkg.go.dev/crypto/rand
.. _crypto/sha256: https://pkg.go.dev/crypto/sha256
.. _snapd library: https://github.com/canonical/snapd
.. _cloud-init: https://cloud-init.io