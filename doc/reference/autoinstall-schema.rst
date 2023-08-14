.. _autoinstall_schema:

Autoinstall schema
******************

The server installer validates the provided autoinstall config against a
:ref:`JSON schema<autoinstall_JSON_schema>`.

How the config is validated
===========================

Although the schema is presented below as a single document, and if you want
to pre-validate your config you should validate it against this document, the
config is not actually validated against this document at run time. What
happens instead is that some sections are loaded, validated, and applied
first, before all other sections are validated. In detail:

1. The reporting section is loaded, validated and applied.
2. The error commands are loaded and validated.
3. The early commands are loaded and validated.
4. The early commands, if any, are run.
5. The config is reloaded, and now all sections are loaded and validated.

This is so that validation errors in most sections can be reported via the
reporting and error-commands configuration, as all other errors are.

.. _autoinstall_JSON_schema:

Schema
======

The `JSON schema`_ for autoinstall data is as follows:

.. code-block:: JSON

    "type": "object",
    "properties": {
        "version": {
            "type": "integer",
            "minimum": 1,
            "maximum": 1
        },
        "early-commands": {
            "type": "array",
            "items": {
                "type": [
                    "string",
                    "array"
                ],
                "items": {
                    "type": "string"
                }
            }
        },
        "reporting": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string"
                    }
                },
                "required": [
                    "type"
                ],
                "additionalProperties": true
            }
        },
        "error-commands": {
            "type": "array",
            "items": {
                "type": [
                    "string",
                    "array"
                ],
                "items": {
                    "type": "string"
                }
            }
        },
        "user-data": {
            "type": "object"
        },
        "packages": {
            "type": "array",
            "items": {
                "type": "string"
            }
        },
        "debconf-selections": {
            "type": "string"
        },
        "locale": {
            "type": "string"
        },
        "refresh-installer": {
            "type": "object",
            "properties": {
                "update": {
                    "type": "boolean"
                },
                "channel": {
                    "type": "string"
                }
            },
            "additionalProperties": false
        },
        "kernel": {
            "type": "object",
            "properties": {
                "package": {
                    "type": "string"
                },
                "flavor": {
                    "type": "string"
                }
            },
            "oneOf": [
                {
                    "type": "object",
                    "required": [
                        "package"
                    ]
                },
                {
                    "type": "object",
                    "required": [
                        "flavor"
                    ]
                }
            ]
        },
        "keyboard": {
            "type": "object",
            "properties": {
                "layout": {
                    "type": "string"
                },
                "variant": {
                    "type": "string"
                },
                "toggle": {
                    "type": [
                        "string",
                        "null"
                    ]
                }
            },
            "required": [
                "layout"
            ],
            "additionalProperties": false
        },
        "source": {
            "type": "object",
            "properties": {
                "search_drivers": {
                    "type": "boolean"
                },
                "id": {
                    "type": "string"
                }
            }
        },
        "network": {
            "oneOf": [
                {
                    "type": "object",
                    "properties": {
                        "version": {
                            "type": "integer",
                            "minimum": 2,
                            "maximum": 2
                        },
                        "ethernets": {
                            "type": "object",
                            "properties": {
                                "match": {
                                    "type": "object",
                                    "properties": {
                                        "name": {
                                            "type": "string"
                                        },
                                        "macaddress": {
                                            "type": "string"
                                        },
                                        "driver": {
                                            "type": "string"
                                        }
                                    },
                                    "additionalProperties": false
                                }
                            }
                        },
                        "wifis": {
                            "type": "object",
                            "properties": {
                                "match": {
                                    "type": "object",
                                    "properties": {
                                        "name": {
                                            "type": "string"
                                        },
                                        "macaddress": {
                                            "type": "string"
                                        },
                                        "driver": {
                                            "type": "string"
                                        }
                                    },
                                    "additionalProperties": false
                                }
                            }
                        },
                        "bridges": {
                            "type": "object"
                        },
                        "bonds": {
                            "type": "object"
                        },
                        "tunnels": {
                            "type": "object"
                        },
                        "vlans": {
                            "type": "object"
                        }
                    },
                    "required": [
                        "version"
                    ]
                },
                {
                    "type": "object",
                    "properties": {
                        "network": {
                            "type": "object",
                            "properties": {
                                "version": {
                                    "type": "integer",
                                    "minimum": 2,
                                    "maximum": 2
                                },
                                "ethernets": {
                                    "type": "object",
                                    "properties": {
                                        "match": {
                                            "type": "object",
                                            "properties": {
                                                "name": {
                                                    "type": "string"
                                                },
                                                "macaddress": {
                                                    "type": "string"
                                                },
                                                "driver": {
                                                    "type": "string"
                                                }
                                            },
                                            "additionalProperties": false
                                        }
                                    }
                                },
                                "wifis": {
                                    "type": "object",
                                    "properties": {
                                        "match": {
                                            "type": "object",
                                            "properties": {
                                                "name": {
                                                    "type": "string"
                                                },
                                                "macaddress": {
                                                    "type": "string"
                                                },
                                                "driver": {
                                                    "type": "string"
                                                }
                                            },
                                            "additionalProperties": false
                                        }
                                    }
                                },
                                "bridges": {
                                    "type": "object"
                                },
                                "bonds": {
                                    "type": "object"
                                },
                                "tunnels": {
                                    "type": "object"
                                },
                                "vlans": {
                                    "type": "object"
                                }
                            },
                            "required": [
                                "version"
                            ]
                        }
                    },
                    "required": [
                        "network"
                    ]
                }
            ]
        },
        "ubuntu-pro": {
            "type": "object",
            "properties": {
                "token": {
                    "type": "string",
                    "minLength": 24,
                    "maxLength": 30,
                    "pattern": "^C[1-9A-HJ-NP-Za-km-z]+$",
                    "description": "A valid token starts with a C and is followed by 23 to 29 Base58 characters.\nSee https://pkg.go.dev/github.com/btcsuite/btcutil/base58#CheckEncode"
                }
            }
        },
        "ubuntu-advantage": {
            "type": "object",
            "properties": {
                "token": {
                    "type": "string",
                    "minLength": 24,
                    "maxLength": 30,
                    "pattern": "^C[1-9A-HJ-NP-Za-km-z]+$",
                    "description": "A valid token starts with a C and is followed by 23 to 29 Base58 characters.\nSee https://pkg.go.dev/github.com/btcsuite/btcutil/base58#CheckEncode"
                }
            },
            "deprecated": true,
            "description": "Compatibility only - use ubuntu-pro instead"
        },
        "proxy": {
            "type": [
                "string",
                "null"
            ],
            "format": "uri"
        },
        "apt": {
            "type": "object",
            "properties": {
                "preserve_sources_list": {
                    "type": "boolean"
                },
                "primary": {
                    "type": "array"
                },
                "mirror-selection": {
                    "type": "object",
                    "properties": {
                        "primary": {
                            "type": "array",
                            "items": {
                                "anyOf": [
                                    {
                                        "type": "string",
                                        "const": "country-mirror"
                                    },
                                    {
                                        "type": "object",
                                        "properties": {
                                            "uri": {
                                                "type": "string"
                                            },
                                            "arches": {
                                                "type": "array",
                                                "items": {
                                                    "type": "string"
                                                }
                                            }
                                        },
                                        "required": [
                                            "uri"
                                        ]
                                    }
                                ]
                            }
                        }
                    }
                },
                "geoip": {
                    "type": "boolean"
                },
                "sources": {
                    "type": "object"
                },
                "disable_components": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "universe",
                            "multiverse",
                            "restricted",
                            "contrib",
                            "non-free"
                        ]
                    }
                },
                "preferences": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "package": {
                                "type": "string"
                            },
                            "pin": {
                                "type": "string"
                            },
                            "pin-priority": {
                                "type": "integer"
                            }
                        },
                        "required": [
                            "package",
                            "pin",
                            "pin-priority"
                        ]
                    }
                },
                "fallback": {
                    "type": "string",
                    "enum": [
                        "abort",
                        "continue-anyway",
                        "offline-install"
                    ]
                }
            }
        },
        "storage": {
            "type": "object"
        },
        "identity": {
            "type": "object",
            "properties": {
                "realname": {
                    "type": "string"
                },
                "username": {
                    "type": "string"
                },
                "hostname": {
                    "type": "string"
                },
                "password": {
                    "type": "string"
                }
            },
            "required": [
                "username",
                "hostname",
                "password"
            ],
            "additionalProperties": false
        },
        "ssh": {
            "type": "object",
            "properties": {
                "install-server": {
                    "type": "boolean"
                },
                "authorized-keys": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    }
                },
                "allow-pw": {
                    "type": "boolean"
                }
            }
        },
        "snaps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string"
                    },
                    "channel": {
                        "type": "string"
                    },
                    "classic": {
                        "type": "boolean"
                    }
                },
                "required": [
                    "name"
                ],
                "additionalProperties": false
            }
        },
        "active-directory": {
            "type": "object",
            "properties": {
                "admin-name": {
                    "type": "string"
                },
                "domain-name": {
                    "type": "string"
                }
            },
            "additionalProperties": false
        },
        "codecs": {
            "type": "object",
            "properties": {
                "install": {
                    "type": "boolean"
                }
            }
        },
        "drivers": {
            "type": "object",
            "properties": {
                "install": {
                    "type": "boolean"
                }
            }
        },
        "oem": {
            "type": "object",
            "properties": {
                "install": {
                    "oneOf": [
                        {
                            "type": "boolean"
                        },
                        {
                            "type": "string",
                            "const": "auto"
                        }
                    ]
                }
            },
            "required": [
                "install"
            ]
        },
        "timezone": {
            "type": "string"
        },
        "updates": {
            "type": "string",
            "enum": [
                "security",
                "all"
            ]
        },
        "late-commands": {
            "type": "array",
            "items": {
                "type": [
                    "string",
                    "array"
                ],
                "items": {
                    "type": "string"
                }
            }
        },
        "shutdown": {
            "type": "string",
            "enum": [
                "reboot",
                "poweroff"
            ]
        }
    },
    "required": [
        "version"
    ],
    "additionalProperties": true
    }

Regeneration
============

The schema above can be regenerated by running ``make schema`` in a Subiquity
source checkout.

.. LINKS 

.. _JSON schema: https://json-schema.org/
