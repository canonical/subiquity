.. _autoinstall_validation:

Autoinstall Validation
=====================================

The following how-to guide demonstrates how to perform pre-validation of a autoinstall config.

Autoinstall config is validated against a :doc:`JSON schema <../reference/autoinstall-schema>` during runtime before it is applied. This check ensures existence of required keys and their data types, but does not guarantee total validity of the data provided (see the :ref:`Validator Limitations<validator-limitations>` section for more details).

Pre-validating the Autoinstall configuration
--------------------------------------------

You can validate autoinstall config prior to install time by using the `validate-autoinstall-user-data script <https://github.com/canonical/subiquity/blob/main/scripts/validate-autoinstall-user-data.py>`_ in the Subiquity GitHub repository.

Getting Started
^^^^^^^^^^^^^^^

Running the validation script requires downloading the Subiquity source code and installing the development dependencies. First, clone the Subiquity repository and ``cd`` into the root of the repository:

.. code:: none

   git clone https://github.com/canonical/subiquity.git && cd subiquity/

Then the required dependencies can be installed by running:

.. code:: none

   make install_deps


Now you can invoke the validation script with:

.. code:: none

   ./scripts/validate-autoinstall-user-data.py <path-to-config>


or you can feed the configuration data via stdin:


.. code:: none

   # a trivial example
   cat <config> | ./scripts/validate-autoinstall-user-data.py

.. warning::

   Never run the validation script as ``sudo``.

Finally, after running the validation script it will report the result of the validation attempt:

.. code:: none

   $ ./scripts/validate-autoinstall-user-data.py <path-to-config>
   Success: The provided autoinstall config validated successfully

You can also use the exit codes to determine the result: 0 (success) or 1 (failure).


Choice of Delivery Method
^^^^^^^^^^^^^^^^^^^^^^^^^

By default the validation script will expect your autoinstall configuration to be passed via cloud-config and expects a valid cloud-config file containing an ``autoinstall`` section:

.. code:: none

   #cloud-config

   # some cloud-init directives

   autoinstall:
      # autoinstall directives

This allows you to use the script directly on your cloud-config data. The validation script will extract the autoinstall configuration from the provided cloud-config data and perform the validation on the extracted autoinstall section directly.


If you want to validate autoinstall configurations which will be delivered via the installation media, like the following example:

.. code:: none

   autoinstall:
      # autoinstall directives

then this can be signaled by passing the ``--no-expect-cloudconfig`` flag. Both formats in this delivery method, with or without a top-level ``autoinstall`` keyword, are supported in this mode.

.. _validator-limitations:

Validator Limitations
---------------------

The autoinstall validator currently has the following limitations:

1. The validator makes an assumption about the target installation media that may not necessarily be true about the actual installation media. It assumes that (1) the installation target is ubuntu-server and (2) the only valid install source is :code:`synthesized`. Some cases where this would cause the validator fail otherwise correct autoinstall configurations:

   a. Missing both an :code:`identity` and :code:`user-data` section for a Desktop target, where these sections are fully optional.
   b. A :code:`source` section which specifies any :code:`id` other than :code:`synthesized`, where the :code:`id` may really match a valid source on the target ISO.

2. Validity of the data provided in each section is not guaranteed as some sections cannot be reasonably validated outside of the installation runtime environment (e.g., a bad :ref:`match directive <disk_selection_extensions>`).

3. The validator is unable to replicate some of the cloud-config based :ref:`delivery checks <how_the_delivery_is_verified>`. There are some basic checks performed to catch simple delivery-related errors, which you can read more about in the examples section, but the focus of the validation is on the Autoinstall configuration *after* it has been delivered to the installer.

.. note::
   See the cloud-init documentation for `how to validate your cloud-config`_.


------------

Examples
--------

Common mistake #1
^^^^^^^^^^^^^^^^^

If a top level ``autoinstall`` keyword is not found in the provided cloud-config during runtime then the installer will miss the autoinstall config and present an interactive session. To prevent occurrences of this issue, the validation script will report a failure if the provided cloud-config does not contain an autoinstall section. *This does not indicate a crash at runtime*, as you can definitely provide cloud-config without autoinstall, but it is a useful result for checking a common formatting mistake.

.. tabs::

   .. tab:: Validation output


      Validating cloud-config which is missing the ``autoinstall`` keyword:

      .. code:: none

         $ ./scripts/validate-autoinstall-user-data.py <path-to-config>
         AssertionError: Expected data to be wrapped in cloud-config but could not find top level 'autoinstall' key.
         Failure: The provided autoinstall config did not validate successfully

   .. tab:: Faulty config

      As an example, the following cloud-config contains an autoinstall section but has misspelled the ``autoinstall`` keyword:

      .. code:: none

         #cloud-config
         autoinstll:
            # autoinstall directives


Common Mistake #2
^^^^^^^^^^^^^^^^^

Another common mistake is to forget the ``#cloud-config`` header in the cloud-config file, which will result in the installer "missing" the autoinstall configuration.

.. tabs::

   .. tab:: Validation output

      The validator will fail the provided cloud-config data if it does not contain the right header:


      .. code:: none

         $ ./scripts/validate-autoinstall-user-data.py <path-to-config>
         AssertionError: Expected data to be wrapped in cloud-config but first line is not '#cloud-config'. Try passing --no-expect-cloudconfig.
         Failure: The provided autoinstall config did not validate successfully


   .. tab:: Faulty config

      Missing the ``#cloud-config`` header will mean the file is not read by cloud-init:

      .. code:: none

         autoinstall:
            # autoinstall directives


Again, this is not indicative of a real runtime error that would appear. Instead, this case would result in having the installer presenting a fully interactive install where a partially or fully automated installation was desired instead.

Common Mistake #3
^^^^^^^^^^^^^^^^^

Another possible mistake is to think that the autoinstall config on the installation media is a cloud-config datasource (it is not):

.. tabs::

   .. tab:: Validation output

      When providing the autoinstall configuration using the top-level ``autoinstall`` keyword format, the installer will verify there are no other top-level keys:

      .. code:: none

         $ ./scripts/validate-autoinstall-user-data.py --no-expect-cloudconfig <path-to-config>
         error: subiquity/load_autoinstall_config/read_config: autoinstall.yaml is not a valid cloud config datasource.
         No other keys may be present alongside 'autoinstall' at the top level.
         Malformed autoinstall in 'top-level keys' section
         Failure: The provided autoinstall config did not validate successfully

   .. tab:: Faulty config

      The following config contains cloud-config directives when it is not expected to contain any:

      .. code:: none

         #cloud-config

         # some cloud-config directives

         autoinstall:
            # autoinstall directives



Debugging errors
^^^^^^^^^^^^^^^^

By default, the validation script has low verbosity output:

.. code:: none

   Malformed autoinstall in 'version or interactive-sections' section
   Failure: The provided autoinstall config did not validate successfully

However, you can increase the output level by successively passing the ``-v`` flag. At maximum verbosity, the validation script will report errors the same way they are reported at runtime.  This is great for inspecting issues in cases where the short error message isn't yet specific enough to be useful and can be used to inspect specific JSON schema validation errors.


.. code:: none

   $ ./scripts/validate-autoinstall-user-data.py autoinstall.yaml  -vvv
   start: subiquity/load_autoinstall_config:
   start: subiquity/load_autoinstall_config/read_config:
   finish: subiquity/load_autoinstall_config/read_config: SUCCESS:
   start: subiquity/Reporting/load_autoinstall_data:
   finish: subiquity/Reporting/load_autoinstall_data: SUCCESS:
   start: subiquity/Error/load_autoinstall_data:
   finish: subiquity/Error/load_autoinstall_data: SUCCESS:
   start: subiquity/core_validation:
   finish: subiquity/core_validation: FAIL: Malformed autoinstall in 'version or interactive-sections' section
   finish: subiquity/load_autoinstall_config: FAIL: Malformed autoinstall in 'version or interactive-sections' section
   Malformed autoinstall in 'version or interactive-sections' section
   Traceback (most recent call last):
     File ".../subiquity/scripts/../subiquity/server/server.py", line 654, in validate_autoinstall
       jsonschema.validate(self.autoinstall_config, self.base_schema)
     File "/usr/lib/python3/dist-packages/jsonschema/validators.py", line 1080, in validate
       raise error
   jsonschema.exceptions.ValidationError: '*' is not of type 'array'

   Failed validating 'type' in schema['properties']['interactive-sections']:
       {'items': {'type': 'string'}, 'type': 'array'}

   On instance['interactive-sections']:
       '*'

   The above exception was the direct cause of the following exception:

   Traceback (most recent call last):
     File ".../subiquity/./scripts/validate-autoinstall-user-data.py", line 186, in verify_autoinstall
       app.load_autoinstall_config(only_early=True, context=None)
     File ".../subiquity/scripts/../subiquitycore/context.py", line 159, in decorated_sync
       return meth(self, **kw)
              ^^^^^^^^^^^^^^^^
     File ".../subiquity/scripts/../subiquity/server/server.py", line 734, in load_autoinstall_config
       self.validate_autoinstall()
     File ".../subiquity/scripts/../subiquity/server/server.py", line 663, in validate_autoinstall
       raise new_exception from original_exception
   subiquity.server.autoinstall.AutoinstallValidationError: Malformed autoinstall in 'version or interactive-sections' section
   Failure: The provided autoinstall config did not validate successfully

In this case, the above output shows that ``interactive-sections`` section failed to validate against the JSON schema because the type provided was a ``string`` and not an ``array`` of ``string`` s.

.. LINKS

.. _how to validate your cloud-config: https://cloudinit.readthedocs.io/en/latest/howto/debug_user_data.html
