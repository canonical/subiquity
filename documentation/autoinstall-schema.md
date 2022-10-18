# JSON Schema for autoinstall config

## Introduction

The server installer validates the provided autoinstall config against a [JSON Schema](#Schema).

## How the config is validated

Although the schema is presented below as a single document, and if you want to pre-validate your config you should validate it against this document, the config is not actually validated against this document at run time. What happens instead is that some sections are loaded, validated and applied first, before all other sections are validated. In detail:

 1. The reporting section is loaded, validated and applied.
 2. The error commands are loaded and validated.
 3. The early commands are loaded and validated.
 4. The early commands, if any, are run.
 5. The config is reloaded, and now all sections are loaded and validated.

This is so that validation errors in most sections can be reported via the reporting and error-commands configuration, as all other errors are.

## Schema

The [JSON schema](https://json-schema.org/) for autoinstall data is as follows:

<pre><code>{
    "type": "object",
    "properties": {
        "version": {
            "type": "integer",
            "minumum": 1,
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
                "geoip": {
                    "type": "boolean"
                },
                "sources": {
                    "type": "object"
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
        }
    },
    "required": [
        "version"
    ],
    "additionalProperties": true
}
</code></pre>

## Regeneration

The schema above can be regenerated by running "make schema" in a subiquity source checkout.
