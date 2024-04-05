.. _providing-autoinstall:

Providing autoinstall configuration
===================================

There are two ways to provide the autoinstall configuration:

* :external+cloud-init:ref:`#cloud-config user data <user_data_formats-cloud_config>` containing ``autoinstall:`` configuration directives for cloud-init
* Directly on the installation media

For detailed how-to guides that provide step-by-step instructions on how to use these two methods, go to:

* :ref:`Autoinstall quick start <autoinstall_quick_start>`
* :ref:`Autoinstall quick start for s390x <autoinstall_quick_start_s390x>`


Autoinstall by way of `cloud-config`
------------------------------------

The suggested way of providing autoinstall configuration to the Ubuntu installer is via cloud-init. This allows the configuration to be applied to the installer without having to modify the installation media.

The autoinstall configuration is provided via cloud-init configuration, which is almost endlessly flexible. In most scenarios the easiest way will be to provide user data via the :external+cloud-init:ref:`datasource_nocloud` data source.

When providing autoinstall via cloud-init, the autoinstall configuration is provided as :external+cloud-init:ref:`user_data_formats-cloud_config`. This means it requires a :code:`#cloud-config` header. The autoinstall directives are placed under a top level :code:`autoinstall:` key:

.. code-block:: yaml

    #cloud-config
    autoinstall:
        version: 1
        ....

.. note::

   :external+cloud-init:ref:`user_data_formats-cloud_config` files must contain the ``#cloud-config`` header to be recognised as a valid cloud configuration data file.


Autoinstall on the installation media
-------------------------------------

Another option for supplying autoinstall to the Ubuntu installer is to place a file named :code:`autoinstall.yaml` on the installation media itself.

The autoinstall configuration provided in this way is passed to the Ubuntu installer directly and does not require the top-level :code:`autoinstall:` key:

.. code-block:: yaml

    version: 1
    ....

Starting in 24.04 (Noble), to be consistent with the cloud-config based format, a top-level :code:`autoinstall:` keyword is allowed:

.. code-block:: yaml

    autoinstall:
        version: 1
        ....

There are two locations that Subiquity checks for the :code:`autoinstall.yaml` file:

* At the root of the installation medium. When writing the installation ISO to a USB flash drive, copy :code:`autoinstall.yaml` to the partition containing the contents of the ISO - i.e. to the directory containing the ``casper`` sub-directory.

* On the root file system of the installation system - this option typically requires modifying the installation ISO and is not recommended.

Alternatively, you can pass the location of the autoinstall file on the kernel command line via the :code:`subiquity.autoinstallpath` parameter, where the path is relative to the root directory of the installation system. For example:

.. code-block::

    subiquity.autoinstallpath=path/to/autoinstall.yaml`


Order of precedence for autoinstall locations
---------------------------------------------

Because there are many ways to specify the autoinstall file, it may happen that multiple locations are specified at the same time. Subiquity searches for the autoinstall file in the following order and uses the first existing one:

1. Kernel command line
2. Root of the installation system
3. `cloud-config`
4. Root of the installation medium (ISO)
