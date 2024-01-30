.. _autoinstall_schema:

Autoinstall schema
==================

The server installer validates the provided autoinstall configuration against a :ref:`JSON schema<autoinstall_JSON_schema>`.

How the configuration is validated
----------------------------------

This reference manual presents the schema as a single document. Use it pre-validate your configuration.

At run time, the configuration is not validated against this document. Instead, configuration sections are loaded and validated in this order:

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
