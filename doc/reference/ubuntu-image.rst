ubuntu-image syntax and options
===============================

``ubuntu-image`` is a program for generating bootable disk images. It supports building snap_-based and classical preinstalled Ubuntu images.


Snap-based images
-----------------

Snap-based images are built from a *model assertion*, which is a YAML file describing a particular combination of core, kernel, and gadget snaps, along with other declarations, signed with a digital signature asserting its authenticity.  The assets defined in the model assertion uniquely describe the device for which the image is built.


Classical images
----------------

Classical images are built from a local `gadget tree`_ path.  The `gadget tree`_ is a primed `gadget snap`_ containing a ``gadget.yaml`` file in the ``meta`` directory and all the necessary bootloader gadget bits built. For instance, a `gadget tree`_ can be prepared by fetching a specially tailored `gadget snap`_ source and running ``snapcraft prime`` on it, with the resulting tree being stored in the ``prime/`` directory.


The ``gadget.yaml`` file
------------------------

As part of the model assertion, a `gadget snap`_ is specified.  The gadget contains a ``gadget.yaml`` file, which contains the exact description of the disk-image contents in the YAML format.  The ``gadget.yaml`` file describes, among other things:

* Names of all the volumes to be produced (volumes are roughly analogous to disk images).

* Structures (structures define the layout of the volume, including partitions, Master Boot Records, or any other relevant content.) within the volume. :none:`wokeignore:rule=master,`

* Whether the volume contains a bootloader and if so, what kind of bootloader.

Note that ``ubuntu-image`` communicates with the Snap Store using the ``snap prepare-image`` sub-command.  The model-assertion file is passed to ``snap prepare-image``, which handles downloading the appropriate gadget and any extra snaps.  See the :manualpage:`snap(8) manual page <man8/snap.8.html>` for additional details.


Basic syntax
------------

.. code-block:: yaml

    ubuntu-image snap [options] model.assertion

    ubuntu-image classic [options] image_definition.yaml


General options
~~~~~~~~~~~~~~~

-h, --help
    Show the help message and exit.

--version
    Show the program version number and exit.


Options of the ``snap`` command
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

These are the options for defining the contents of snap-based images.  They can only be used when the ``ubuntu-image snap`` command is used.

``model_assertion``
    Path to the model assertion file.  This positional argument must be given for this mode of operation.

--cloud-init USER-DATA-FILE
    ``cloud-config`` data to be copied to the image.

--disable-console-conf
    Disable ``console-conf`` on the resulting image.

--factory-image
    Hint that the image is meant to boot in a device factory.

--validation=<ignore|enforce>
    Control whether validations should be ignored or enforced.

--snap SNAP
    Install an extra snap.  This is passed through to ``snap prepare-image``. The snap argument can include additional information about the channel and/or risk with the following syntax: ``<snap>=<channel|risk>``. Note that this flag will cause an error if the model assertion has a grade higher than dangerous.

--revision <SNAP_NAME:REVISION>
    Install a specific revision of a snap rather than the latest available in a particular channel. The snap specified with ``SNAP_NAME`` must be included either in the model assertion or as an argument to ``--snap``. If both a revision and channel are provided, the revision specified is installed in the image, and updates come from the specified channel.

--preseed
    Preseed the image (Ubuntu Core 20 and higher only).

--preseed-sign-key=<key>
    Name of the key to use to sign the preseed assertion, otherwise use the default key.

--sysfs-overlay=<path to directory that contains sysfs overlay>
    Specify the directory that contains the sysfs overlay. This options also requires the ``--preseed`` and ``--preseed-sign-key`` options.

Options of the ``classic`` command
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

These are the options for defining the contents of classical preinstalled Ubuntu images. They can only be used when the ``ubuntu-image classic`` command is used.

``image_definition``
    Path to the image-definition file. This file defines all of the customisation required when building the image. This positional argument must be given for this mode of operation.


Common options
~~~~~~~~~~~~~~

There are two general operational modes to ``ubuntu-image``.  The usual mode is to run the script giving the required model-assertion file as a required positional argument, generating a disk image file.  These options are useful in this mode of operation.

The second mode of operation is provided for debugging and testing purposes. It allows you to run the internal state machine step by step and is described in more detail below.

-d, --debug
    Enable debugging output.

--verbose
    Enable verbose output.

--quiet
    Only print error messages. Suppress all other output.

-O DIRECTORY, --output-dir DIRECTORY
    Write generated disk-image files to this directory.  The files will be named after the ``gadget.yaml`` volume names, with the ``.img`` suffix appended.  If not given, the value of the ``--workdir`` flag is used if specified.  If neither ``--output-dir`` nor ``--workdir`` is used, the image(s) will be placed in the current working directory.  This option replaces, and cannot be used with, the deprecated ``--output`` option.

-i SIZE, --image-size SIZE
    The size of the generated disk-image files.  If this size is smaller than the minimum calculated size of the volume, a warning is issued and ``--image-size`` is ignored.  The value is the size in bytes, with allowable suffixes ``M`` for MiB and ``G`` for GiB.

    An extended syntax is supported for ``gadget.yaml`` files that specify multiple volumes (i.e. disk images).  In that case, a single ``SIZE`` argument is used for all the defined volumes, with the same rules for ignoring values that are too small.  You can specify the image size for a single volume using an indexing prefix on the ``SIZE`` parameter, where the index is either a volume name or an integer index starting at zero. For example, to set the image size only on the second volume, which might be called ``sdcard`` in ``gadget.yaml``, use: ``--image-size 1:8G`` (the number ``1`` index indicates the second volume; volumes are 0-indexed). Or use ``--image-size sdcard:8G``.

    You can also specify multiple volume sizes by separating them with commas, and you can mix and match integer indices and volume-name indices.  Thus, if ``gadget.yaml`` names three volumes, and you want to set all three to different sizes, you can use ``--image-size 0:2G,sdcard:8G,eMMC:4G``.

    In the case of ambiguities, the size hint is ignored, and the calculated size for the volume is used instead.

--disk-info DISK-INFO-CONTENTS
    File to be used as ``.disk/info`` on the root file system of the image.  This file can contain useful information about the target image, such as image identification data, system name, build timestamp, etc.

-c CHANNEL, --channel CHANNEL
    The default Snap channel to use while preseeding the image.

--sector-size SIZE
    When creating the disk-image file, use the given sector size.  This can be either 512 or 4096 (4k sector size), defaulting to 512.


State-machine options
~~~~~~~~~~~~~~~~~~~~~

.. caution:: The options described here are primarily for debugging and testing purposes and should not be considered part of the stable, public API.  State-machine step numbers and names can change between releases.

``ubuntu-image`` internally runs a state machine to create the disk image. These are some options for controlling this state machine.  Other than ``--workdir``, these options are mutually exclusive.  When ``--until`` or ``--thru`` is given, the state machine can be resumed later with ``--resume``, but ``--workdir`` must be given in that case since the state is saved in a ``ubuntu-image.json`` file in the working directory.

-w DIRECTORY, --workdir DIRECTORY
    The working directory in which to download and unpack all the source files for the image.  This directory can exist or not, and it is not removed after this program exits.  If not given, a temporary working directory is used instead, which *is* deleted after this program exits.  Use ``--workdir`` if you want to be able to resume a partial state-machine run.  The ``gadget.yaml`` file is copied to the working directory after it's downloaded.

-u STEP, --until STEP
    Run the state machine until the given ``STEP``, non-inclusively.  ``STEP`` is the name of a state-machine method. See the `List of steps`_.

-t STEP, --thru STEP
    Run the state machine until the given ``STEP``, inclusively.  ``STEP`` is the name of a state-machine method. See the `List of steps`_.

-r, --resume
    Continue the state machine from the previously saved state.  It returns an error if there is no previous state.


Files used by ``ubuntu-image``
------------------------------

* |gadgetyaml|_
* `model assertion`_
* `gadget tree`_ (example)
* `cloud-config`_


Environment variables
---------------------

The following environment variables are recognised by ``ubuntu-image``.

``UBUNTU_IMAGE_PRESERVE_UNPACK``
    When set, the variable specifies the directory for preserving a pristine copy of the unpacked gadget contents.  The directory must exist, and an ``unpack`` directory will be created under this directory.  The full contents of the ``<workdir>/unpack`` directory after the ``snap prepare-image`` sub-command has run is copied here.

There are a few other environment variables used for building and testing only.


.. _list of steps:

List of steps
-------------

The names of steps that can be used with ``--until`` and ``--thru`` for each image type are listed below.

Classical-image steps
~~~~~~~~~~~~~~~~~~~~~

State machines are dynamically created for classical-image builds based on the contents of the image definition. The list of all possible states is as follows:

#. ``make_temporary_directories``
#. ``parse_image_definition``
#. ``calculate_states``
#. ``build_gadget_tree``
#. ``prepare_gadget_tree``
#. ``load_gadget_yaml``
#. ``create_chroot``
#. ``germinate``
#. ``add_extra_ppas``
#. ``install_packages``
#. ``clean_extra_ppas``
#. ``verify_artifact_names``
#. ``customize_cloud_init``
#. ``customize_fstab``
#. ``manual_customization``
#. ``preseed_image``
#. ``clean_rootfs``
#. ``populate_rootfs_contents``
#. ``generate_disk_info``
#. ``calculate_rootfs_size``
#. ``populate_bootfs_contents``
#. ``populate_prepare_partitions``
#. ``make_disk``
#. ``generate_package_manifest``

To check the steps that are going to be used for a specific image-definition file, use the ``--print-states`` flag.

Snap-image steps
~~~~~~~~~~~~~~~~

#. ``make_temporary_directories``
#. ``prepare_image``
#. ``load_gadget_yaml``
#. ``populate_rootfs_contents``
#. ``generate_disk_info``
#. ``calculate_rootfs_size``
#. ``populate_bootfs_contents``
#. ``populate_prepare_partitions``
#. ``make_disk``
#. ``generate_snap_manifest``


Additional resources
--------------------

* :manualpage:`snap(8) manual page <man8/snap.8.html>`


.. |gadgetyaml| replace:: ``gadget.yaml``

.. LINKS

.. _snap: http://snapcraft.io/
.. _gadget snap: https://snapcraft.io/docs/the-gadget-snap
.. _gadget tree: https://github.com/snapcore/pc-gadget
.. _image_definition.yaml: https://github.com/canonical/ubuntu-image/tree/main/internal/imagedefinition#readme
.. _gadgetyaml: https://forum.snapcraft.io/t/gadget-snaps/696
.. _model assertion: https://ubuntu.com/core/docs/reference/assertions/model
.. _gadget tree: https://github.com/snapcore/pc-gadget
.. _cloud-config: https://help.ubuntu.com/community/CloudInit
