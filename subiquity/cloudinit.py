"""Shared cloudinit utility functions"""

import json


def get_host_combined_cloud_config() -> dict:
    """Return the host system /run/cloud-init/combined-cloud-config.json"""
    try:
        with open("/run/cloud-init/combined-cloud-config.json") as fp:
            return json.load(fp)
    except (IOError, OSError, AttributeError, json.decoder.JSONDecodeError):
        return {}
