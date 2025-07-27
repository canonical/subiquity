ubuntu-image syntax and options
===============================

``ubuntu-image`` is a program for generating bootable disk images. It supports building snap_-based and classical preinstalled Ubuntu images.


Installing ``ubuntu-image``
---------------------------

The ``ubuntu-image`` tool is distributed as a snap package through the Snap Store: `ubuntu-image <https://snapcraft.io/ubuntu-image>`_. Install it either from a Snap-enabled software store provided by your distribution, or by running this command with ``sudo`` or as the ``root`` user:

.. code-block::

    snap install ubuntu-image --classic

Note that you need have the snap daemon installed. See `Installing the daemon <https://snapcraft.io/docs/installing-snapd>`_ for instructions for your distribution.


Snap-based images
-----------------

Snap-based images are built from a *model assertion*, which is a YAML file describing a particular combination of core, kernel, and gadget snaps, along with other declarations, signed with a digital signature asserting its authenticity.  The assets defined in the model assertion uniquely describe the device for which the image is built. See `model assertion`_ for details.


Classical images
----------------

Classical images are built from an image-definition YAML file, which defines the image content and resulting output format. Key elements of this configuration are the following sections:

``gadget``
    Defines how to get the gadget required to build boot assets and the partition layout.

``rootfs``
    Defines the parameters to build the content of the rootfs.

``artifacts``
    Defines the types of artifacts to create, including the actual images, manifest files, and others.


The ``gadget.yaml`` file
------------------------

As part of the model assertion, a `gadget snap`_ is specified.  The gadget contains a ``gadget.yaml`` file, which contains the exact description of the disk-image contents in the YAML format.  The ``gadget.yaml`` file describes, among other things:

* Names of all the volumes to be produced (volumes are roughly analogous to disk images).

* Structures (structures define the layout of the volume, including partitions, Primary Boot Records, or any other relevant content.) within the volume.

* Whether the volume contains a bootloader and if so, what kind of bootloader.

Note that ``ubuntu-image`` communicates with the Snap Store using the ``Prepare()`` function from the snapd library.  The model-assertion file is passed to the function, which handles downloading the appropriate gadget and any extra snaps.


Basic syntax
------------

The ``ubuntu-image`` tool requires administrative privileges. Run it with ``sudo`` or as the ``root`` user. Note that the tool does not check whether it's executed with sufficient rights or not.

.. code-block:: yaml

    ubuntu-image snap [options] model.assertion

    ubuntu-image classic [options] image_definition.yaml

.. note:: ``ubuntu-image`` requires **elevated permissions**. Run it as **root** or with ``sudo``.

General options
~~~~~~~~~~~~~~~

-h, --help
    Show the help message and exit.

--version
    Show the program version number and exit.


Common options
~~~~~~~~~~~~~~

There are two general operational modes to ``ubuntu-image``.  The usual mode is to run the tool giving the required model-assertion file as a required positional argument, generating a disk image file.  These options are useful in this mode of operation.

The second mode of operation is provided for debugging and testing purposes. It allows you to run the internal state machine step by step and is described in more detail below.

-d, --debug
    Enable debugging output.

--verbose
    Enable verbose output.

--quiet
    Only print error messages. Suppress all other output.

-O DIRECTORY, --output-dir DIRECTORY
    Write generated disk-image files to this directory.  The files will be named after the ``gadget.yaml`` volume names, with the ``.img`` suffix appended.  If not given, the value of the ``--workdir`` flag is used if specified.  If neither ``--output-dir`` nor ``--workdir`` is used, the image(s) will be placed in the current working directory.  This option replaces, and cannot be used with, the deprecated ``--output`` option.

-w DIRECTORY, --workdir DIRECTORY
    The working directory in which to download and unpack all the source files for the image.  This directory can exist or not, and it is not removed after this program exits.  If not given, a temporary working directory is used instead, which *is* deleted after this program exits.  Use ``--workdir`` if you want to be able to resume a partial state-machine run.  The ``gadget.yaml`` file is copied to the working directory after it's downloaded.

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

--validation=<ignore|enforce>
    Controls whether validations should be ignored or enforced.


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

--snap <SNAP[,SNAP]>
    Install an extra snap or snaps.  The snap argument can include additional information about the channel or risk with the following syntax: ``<snap>=<channel|risk>``. Note that this flag causes an error if the model assertion has a grade higher than dangerous.

--revision <SNAP_NAME:REVISION>
    Install a specific revision of a snap rather than the latest available in a particular channel. The snap specified with ``SNAP_NAME`` must be included either in the model assertion or as an argument to ``--snap``. If both a revision and channel are provided, the revision specified is installed in the image, and updates come from the specified channel.

--preseed
    Preseed the image (Ubuntu Core 20 and higher only).

--preseed-sign-key=<key>
    Name of the key to use to sign the preseed assertion, otherwise use the default key.

--sysfs-overlay=<path to directory that contains sysfs overlay>
    Specify the directory that contains the sysfs overlay. This options also requires the ``--preseed`` and ``--preseed-sign-key`` options.

--assertion=<ASSERTION-FILE-PATH>
    Include in the produced image the assertions contained in the given file. The files can include multiple assertions. The argument can be specified multiple times. All assertion types are allowed, except for ``snap-declaration``, ``snap-revision``, ``model``, ``serial`` and ``validation-set``.

Options of the ``classic`` command
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

These are the options for defining the contents of classical preinstalled Ubuntu images. They can only be used when the ``ubuntu-image classic`` command is used.

``image_definition``
    Path to the image-definition file. This file defines all of the customization required when building the image. This positional argument must be given for this mode of operation.


State-machine options
~~~~~~~~~~~~~~~~~~~~~

.. caution:: The options described here are primarily for debugging and testing purposes and should not be considered part of the stable, public API.  State-machine step numbers and names can change between releases.

``ubuntu-image`` internally runs a state machine to create the disk image. These are some options for controlling this state machine.  Other than ``--workdir``, these options are mutually exclusive.  When ``--until`` or ``--thru`` is given, the state machine can be resumed later with ``--resume``, but ``--workdir`` must be given in that case since the state is saved in a ``ubuntu-image.json`` file in the working directory.

-u STEP, --until STEP
    Run the state machine until the given ``STEP``, non-inclusively.  ``STEP`` is the name of a state-machine method.

-t STEP, --thru STEP
    Run the state machine until the given ``STEP``, inclusively.  ``STEP`` is the name of a state-machine method.

-r, --resume
    Continue the state machine from the previously saved state.  It returns an error if there is no previous state.


Files used by ``ubuntu-image``
------------------------------

* |gadgetyaml|_
* `model assertion`_
* `gadget tree`_ (example)
* `cloud-config`_


Environment variable
--------------------

The following environment variable is recognized by ``ubuntu-image``.

``UBUNTU_IMAGE_PRESERVE_UNPACK``
    When set, the variable specifies the directory for preserving a pristine copy of the unpacked gadget contents.  The directory must exist, and an ``unpack`` directory will be created under this directory.  The full contents of the ``<workdir>/unpack`` directory after the ``snap prepare-image`` sub-command has run is copied here.


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
