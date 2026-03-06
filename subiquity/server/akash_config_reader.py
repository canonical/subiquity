# Copyright 2024 Akash Network
#
# Utility to read install-config.json from an NTFS partition.
# This is used when the Electron installer on Windows writes a config file
# before rebooting into the Ubuntu installer, allowing subiquity to pre-fill
# interactive prompts (installation key, network config).
#
# The config file is only read when the kernel param `akash.auto-config` is
# present in /proc/cmdline (set by the Electron installer's grub.cfg).

import json
import logging
import os
import subprocess
import tempfile

log = logging.getLogger("subiquity.server.akash_config_reader")

CONFIG_PATH = "akash-homenode/install-config.json"

# Cache the config so we only read it once
_cached_config = None
_cache_checked = False


def read_windows_config() -> dict | None:
    """Read install-config.json from an NTFS partition.

    Returns the parsed config dict if found, or None if:
    - akash.auto-config is not in /proc/cmdline
    - No NTFS partition with the config file is found
    - The config file is invalid JSON

    The config is cached after first successful read.
    """
    global _cached_config, _cache_checked

    if _cache_checked:
        return _cached_config

    _cache_checked = True

    # Check for akash.auto-config kernel parameter
    try:
        cmdline = open("/proc/cmdline").read()
        if "akash.auto-config" not in cmdline:
            log.debug("akash.auto-config not in kernel cmdline, skipping config read")
            return None
    except Exception:
        return None

    log.info("akash.auto-config detected, searching for install config on NTFS partitions")

    # Probe NTFS partitions
    for dev in _find_ntfs_partitions():
        mp = tempfile.mkdtemp(prefix="akash-ntfs-")
        try:
            subprocess.run(
                ["mount", "-t", "ntfs3", "-o", "ro", dev, mp],
                check=True,
                capture_output=True,
            )
            config_file = os.path.join(mp, CONFIG_PATH)
            if os.path.exists(config_file):
                with open(config_file) as f:
                    config = json.load(f)
                log.info("Loaded config from %s on %s", CONFIG_PATH, dev)
                _cached_config = config
                return config
            else:
                log.debug("Config file not found on %s", dev)
        except subprocess.CalledProcessError as e:
            log.debug("Failed to mount %s: %s", dev, e.stderr.decode() if e.stderr else str(e))
        except json.JSONDecodeError as e:
            log.warning("Invalid JSON in config file on %s: %s", dev, e)
        except Exception as e:
            log.debug("Failed to read from %s: %s", dev, e)
        finally:
            try:
                subprocess.run(["umount", mp], capture_output=True)
            except Exception:
                pass
            try:
                os.rmdir(mp)
            except Exception:
                pass

    log.info("No install config found on any NTFS partition")
    return None


def _find_ntfs_partitions() -> list[str]:
    """Find all NTFS partitions on the system using lsblk."""
    try:
        result = subprocess.run(
            ["lsblk", "-nrpo", "NAME,FSTYPE"],
            check=True,
            capture_output=True,
            text=True,
        )
        partitions = []
        for line in result.stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 2 and parts[1] in ("ntfs", "ntfs3"):
                partitions.append(parts[0])
        log.debug("Found NTFS partitions: %s", partitions)
        return partitions
    except Exception as e:
        log.debug("Failed to find NTFS partitions: %s", e)
        return []
