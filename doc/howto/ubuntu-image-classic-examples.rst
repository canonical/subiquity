.. _how-to-use-ubuntu-image-with-the-classic-command:

How to use ``ubuntu-image`` with the ``classic`` command
========================================================

The :command:`classic` command in :command:`ubuntu-image` is used to create classical Ubuntu images based on traditional Ubuntu releases (like Desktop or Server images). The :command:`classic` command uses an **image definition** YAML file to define the image structure.

The use of the :command:`snap` command in :command:`ubuntu-image` to generate Ubuntu Core images is described at `Build your first Ubuntu Core image <https://ubuntu.com/core/docs/build-an-image>`__.

.. note:: :command:`ubuntu-image` requires elevated permissions to run correctly. Use :command:`sudo` when running the command.


.. _general-command-structure:

General command structure
-------------------------

The general command to build a classical image is:

.. code-block:: none

    sudo ubuntu-image [options] classic <image-definition.yaml>

Replace ``<image-definition.yaml>`` with the path to the image definition file.

----


.. _building-a-basic-ubuntu-image-for-a-pc:

Building a basic Ubuntu image for a PC
--------------------------------------

In this example, you create a simple classical Ubuntu image for the **amd64** architecture.

#. Create the image definition, :file:`classical-amd64.yaml`, with the following content:

   .. code-block:: yaml

    # Image metadata
    name: ubuntu-classical-amd64
    display-name: Ubuntu Classical Image for amd64
    revision: 1
    architecture: amd64
    series: noble
    class: preinstalled

    # Optional kernel (defaults to 'linux' if omitted)
    kernel: linux-image-generic

    # Gadget snap
    gadget:
      url: https://github.com/canonical/pc-gadget
      branch: classic
      type: git

    # Root filesystem definition
    rootfs:
      components:
        - main
        - restricted
        - universe
        - multiverse
      archive: ubuntu
      mirror: http://archive.ubuntu.com/ubuntu/
      pocket: updates
      seed:
        urls:
          - git://git.launchpad.net/~ubuntu-core-dev/ubuntu-seeds/+git/
        names:
          - server
          - minimal
        branch: noble
        vcs: true
      sources-list-deb822: true

    # Required dependency
    customization:
      extra-snaps:
        - name: snapd

    # Artifacts to generate
    artifacts:
      img:
        - name: ubuntu-classical-amd64.img
      manifest:
        name: ubuntu-classical-amd64.manifest

#. Build the image by running the following command:

   .. code-block:: none

       sudo ubuntu-image classic classical-amd64.yaml

   The expected output looks like this:

   .. code-block:: none

    WARNING: rootfs.sources-list-deb822 is set to true. The DEB822 format
             will be used to manage sources list. Please make sure you are
             not building an image older than noble.
    [0] build_gadget_tree
    [1] prepare_gadget_tree
    [2] load_gadget_yaml
    WARNING: volumes:pc:structure:2:filesystem_label used for defining partition roles; use role instead
    [3] verify_artifact_names
    [4] germinate
    [5] create_chroot
    [6] install_packages
    [7] prepare_image
    [8] preseed_image
    [9] clean_rootfs
    [10] customize_sources_list
    [11] set_default_locale
    [12] populate_rootfs_contents
    [13] generate_disk_info
    [14] calculate_rootfs_size
    [15] populate_bootfs_contents
    [16] populate_prepare_partitions
    [17] make_disk
    [18] update_bootloader
    [19] generate_package_manifest
    Build successful

   The resulting artefacts are:

   * The generated image itself: :file:`ubuntu-classical-amd64.img`
   * The build manifest: :file:`ubuntu-classical-amd64.manifest`


.. _building-a-basic-ubuntu-image-for-raspberry-pi:

Building a basic Ubuntu image for Raspberry Pi
----------------------------------------------

In this example, you create a simple classical Ubuntu image for the Raspberry Pi board.

#. Create the image definition, :file:`classical-raspi.yaml`, with the following content:

   .. code-block:: yaml

    # Image metadata
    name: ubuntu-server-raspi-arm64
    display-name: Ubuntu Server Raspberry Pi arm64
    revision: 1
    architecture: arm64
    series: noble
    class: preinstalled
    kernel: linux-image-raspi

    # Gadget snap
    gadget:
      url: https://git.launchpad.net/snap-pi
      branch: "classic"
      type: "git"

    # Root filesystem definition
    rootfs:
      archive: ubuntu
      sources-list-deb822: true
      components:
        - main
        - restricted
        - universe
        - multiverse
      mirror: http://ports.ubuntu.com/ubuntu-ports/
      pocket: updates
      seed:
        urls:
          - git://git.launchpad.net/~ubuntu-core-dev/ubuntu-seeds/+git/
        branch: noble
        names:
          - server
          - server-raspi
          - raspi-common
          - minimal
          - standard
          - cloud-image
          - supported-raspi-common

    # Additional settings
    customization:
      cloud-init:
        user-data: |
          #cloud-config
          chpasswd:
            expire: true
            users:
              - name: ubuntu
                password: ubuntu
                type: text
      extra-snaps:
        - name: snapd
      fstab:
        - label: "writable"
          mountpoint: "/"
          filesystem-type: "ext4"
          dump: false
          fsck-order: 1
        - label: "system-boot"
          mountpoint: "/boot/firmware"
          filesystem-type: "vfat"
          mount-options: "defaults"
          dump: false
          fsck-order: 1

    # Artifacts to generate
    artifacts:
      img:
        - name: ubuntu-24.04-preinstalled-server-arm64+raspi.img
      manifest:
        name: ubuntu-24.04-preinstalled-server-arm64+raspi.manifest


#. Build the image by running the following command:

   .. code-block:: none

       sudo ubuntu-image classic classical-raspi.yaml


.. _setting-image-size:

Setting image size
------------------

To define a custom size for the generated image, use the ``--image-size`` option. For example, to set the image size to 8 GiB:

.. code-block:: none

    sudo ubuntu-image classic classical-amd64.yaml --image-size=8G

This creates a classical Ubuntu image with a total size of 8 GiB. This is useful when intending to use the image on a medium with a specific capacity.

.. note:: If the requested size is smaller than the minimum calculated size of the image, the ``--image-size`` option is ignored, and a warning is output.


.. _specifying-working-and-output-directories:

Specifying working and output directories
-----------------------------------------

To preserve all the downloaded and unpacked source files used for building the image after the build completes, specify a working directory using the ``--workdir`` option. The directory is created if it doesn't exist.

The generated image is stored in the specified ``--workdir``, unless the ``--output-dir`` option is defined. By default, when neither of these options is used, a temporary working directory is used and deleted after the build, and the generated image is placed in the current directory.

Example:

.. code-block:: none

    sudo ubuntu-image --workdir=/tmp/u-i --output-dir=images classic classical-raspi.yaml

This command leaves all source files used to build the image in the :file:`/tmp/u-i/` directory, and places the generated image into the :file:`images` subdirectory within the current directory.


.. _adding-a-disk-info-file-to-image:

Adding a disk-info file to image
--------------------------------

To add an extra file with information to the generated image, use the ``--disk-info`` option. The file is included in the image as :file:`.disk/info`. This can be useful to store information, for example, about the name of the system, time of build, or other identifying data.

For example, a :file:`disk.info` file could include the following content:

.. code-block:: none
   :caption: ``disk.info``

    Built with: ubuntu-image 3.4.1
    Time: Oct 14 2024, 13.27:11
    Gadget: 64bit PC Gadget Snap

To include it in an image, run:

.. code-block:: none

    sudo ubuntu-image --disk-info disk.info classic classical-amd64.yaml
