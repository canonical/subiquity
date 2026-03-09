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

    log.info("akash.auto-config detected, searching for install config")

    # Phase 0: Check /tmp/install-config.json (placed by early-commands when
    # booting from the Windows installer).  The NTFS partition is locked by
    # casper's ISO loop device, so the config is read from the ESP by an
    # early-command and copied here.  Standalone ISO boots skip this path.
    esp_config = "/tmp/install-config.json"
    try:
        if os.path.exists(esp_config):
            with open(esp_config) as f:
                config = json.load(f)
            log.info("Loaded config from %s (ESP early-command)", esp_config)
            _cached_config = config
            return config
    except json.JSONDecodeError as e:
        log.warning("Invalid JSON in %s: %s", esp_config, e)
    except Exception as e:
        log.debug("Failed to read %s: %s", esp_config, e)

    # Phase 1: Check NTFS partitions that are already mounted (e.g. by casper
    # iso-scan).  When booting via iso-scan/filename, casper mounts the NTFS
    # partition to access the ISO.  Trying to mount the same device again with
    # ntfs3 can fail (EBUSY / driver conflict), so check existing mounts first.
    already_mounted = _find_mounted_ntfs()
    for dev, mp in already_mounted.items():
        config_file = os.path.join(mp, CONFIG_PATH)
        log.debug("Checking existing mount %s (%s) for %s", mp, dev, CONFIG_PATH)
        try:
            if os.path.exists(config_file):
                with open(config_file) as f:
                    config = json.load(f)
                log.info("Loaded config from existing mount %s (%s)", mp, dev)
                _cached_config = config
                return config
        except json.JSONDecodeError as e:
            log.warning("Invalid JSON in config on %s (%s): %s", mp, dev, e)
        except Exception as e:
            log.debug("Failed to read from existing mount %s: %s", mp, e)

    # Phase 2: Try mounting NTFS partitions that are NOT already mounted
    mounted_devs = set(already_mounted.keys())
    for dev in _find_ntfs_partitions():
        if dev in mounted_devs:
            continue  # Already checked in phase 1
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


def _find_mounted_ntfs() -> dict[str, str]:
    """Find NTFS partitions that are already mounted (e.g. by casper iso-scan).

    Returns a dict mapping device path -> mount point.
    """
    mounted = {}
    try:
        with open("/proc/mounts") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 3:
                    continue
                dev, mp, fstype = parts[0], parts[1], parts[2]
                if fstype in ("ntfs", "ntfs3", "fuseblk"):
                    # fuseblk is used by ntfs-3g (FUSE)
                    mounted[dev] = mp
        if mounted:
            log.debug("Found already-mounted NTFS partitions: %s", mounted)
    except Exception as e:
        log.debug("Failed to read /proc/mounts: %s", e)
    return mounted


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
