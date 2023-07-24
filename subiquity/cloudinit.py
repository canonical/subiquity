"""Shared cloudinit utility functions"""

import json
import logging

log = logging.getLogger("subiquity.cloudinit")


def get_host_combined_cloud_config() -> dict:
    """Return the host system /run/cloud-init/combined-cloud-config.json"""
    try:
        with open("/run/cloud-init/combined-cloud-config.json") as fp:
            config = json.load(fp)
            log.debug(
                "Loaded cloud config from /run/cloud-init/combined-cloud-config.json"
            )
            return config
    except (IOError, OSError, AttributeError, json.decoder.JSONDecodeError):
        log.debug("Failed to load combined-cloud-config")
        return {}
