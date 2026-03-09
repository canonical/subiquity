# Copyright 2024 Akash Network
#
# Utility to read install-config.json written by the Windows Electron installer.
# Supports two locations:
#   1. ESP (FAT32 EFI System Partition) at EFI/akash-installer/install-config.json
#      — used when booting from Windows (NTFS is locked by casper's ISO loop device)
#   2. NTFS partition at akash-homenode/install-config.json (legacy/fallback)
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
ESP_CONFIG_PATH = "EFI/akash-installer/install-config.json"

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

    # Phase 0: Check the ESP (FAT32 EFI System Partition).
    # When booting from the Windows installer, the NTFS partition is locked by
    # casper's ISO loop device (device busy).  The Electron app writes
    # install-config.json to the ESP alongside the boot files, so we mount
    # the ESP directly and read from there.  Standalone ISO boots won't have
    # the config on the ESP, so this falls through to NTFS phases.
    config = _check_esp_config()
    if config is not None:
        _cached_config = config
        return config

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


def _find_vfat_partitions() -> list[str]:
    """Find all FAT32/vfat partitions (potential ESPs) using lsblk."""
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
            if len(parts) >= 2 and parts[1] == "vfat":
                partitions.append(parts[0])
        log.debug("Found vfat partitions: %s", partitions)
        return partitions
    except Exception as e:
        log.debug("Failed to find vfat partitions: %s", e)
        return []


def _check_esp_config() -> dict | None:
    """Mount each vfat (ESP) partition and look for install-config.json."""
    for dev in _find_vfat_partitions():
        mp = tempfile.mkdtemp(prefix="akash-esp-")
        try:
            subprocess.run(
                ["mount", "-t", "vfat", "-o", "ro", dev, mp],
                check=True,
                capture_output=True,
            )
            config_file = os.path.join(mp, ESP_CONFIG_PATH)
            if os.path.exists(config_file):
                with open(config_file) as f:
                    config = json.load(f)
                log.info("Loaded config from ESP %s (%s)", dev, config_file)
                return config
            else:
                log.debug("Config not found on ESP %s", dev)
        except subprocess.CalledProcessError as e:
            log.debug(
                "Failed to mount ESP %s: %s",
                dev,
                e.stderr.decode() if e.stderr else str(e),
            )
        except json.JSONDecodeError as e:
            log.warning("Invalid JSON in ESP config on %s: %s", dev, e)
        except Exception as e:
            log.debug("Failed to read ESP %s: %s", dev, e)
        finally:
            try:
                subprocess.run(["umount", mp], capture_output=True)
            except Exception:
                pass
            try:
                os.rmdir(mp)
            except Exception:
                pass
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
