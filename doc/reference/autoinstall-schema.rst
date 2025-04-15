.. _autoinstall_schema:

Autoinstall schema
==================

The server installer validates the provided autoinstall configuration against a :ref:`JSON schema<autoinstall_JSON_schema>`. The end of this reference manual presents the schema as a single document which could be used to manually pre-validate an autoinstall configuration, however the actual runtime validation process is more involved than a simple JSON schema validation. See the provided :doc:`pre-validation script <../howto/autoinstall-validation>` for how to perform autoinstall pre-validation.

.. _how_the_delivery_is_verified:

How the delivery is verified
----------------------------

To ensure expected runtime behavior after delivering the autoinstall config, the installer performs some quick checks to ensure one delivery method is not confused for another.

cloud-config
^^^^^^^^^^^^

When passing autoinstall via cloud-config, the installer will inspect the cloud-config data for any autoinstall-specific keywords outside of the top-level ``autoinstall`` keyword in the config and throw an error if any are encountered. If there are no misplaced keys, the data within the ``autoinstall`` section is passed to the installer.


Installation Media
^^^^^^^^^^^^^^^^^^

When passing autoinstall via the installation media and using the top-level ``autoinstall`` keyword format, the installer will inspect the passed autoinstall file to guarantee that there are no other top-level keys. This check guarantees that the autoinstall config is not mistaken for a cloud-config datasource.

How the configuration is validated
----------------------------------

After the configuration has been delivered to the installer successfully, the configuration sections are loaded and validated in this order:

1. The reporting section is loaded, validated and applied.
2. The error commands are loaded and validated.
3. The early commands are loaded and validated.
4. The early commands, if any, are run.
5. The configuration is reloaded, and all sections are loaded and validated.

This is to ensure that potential validation errors in most sections can be reported using the reporting and error-commands configuration the same way as other errors.

.. _autoinstall_JSON_schema:

Schema
------

The `JSON schema`_ for autoinstall data:

.. literalinclude:: ../../autoinstall-schema.json
   :language: JSON

Regeneration
------------

To regenerate the schema, run ``make schema`` in the root directory of the `Subiquity source repository`_.

.. LINKS

.. _JSON schema: https://json-schema.org/
.. _Subiquity source repository: https://github.com/canonical/subiquity
