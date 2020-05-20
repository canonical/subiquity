import copy
import glob
import fnmatch
import os
import logging
import yaml

log = logging.getLogger("subiquitycore.netplan")


def _sanitize_inteface_config(iface_config):
    for ap, ap_config in iface_config.get('access-points', {}).items():
        if 'password' in ap_config:
            ap_config['password'] = '<REDACTED>'


def sanitize_interface_config(iface_config):
    iface_config = copy.deepcopy(iface_config)
    _sanitize_inteface_config(iface_config)
    return iface_config


def sanitize_config(config):
    """Return a copy of config with passwords redacted."""
    config = copy.deepcopy(config)
    interfaces = config.get('network', {}).get('wifis', {}).items()
    for iface, iface_config in interfaces:
        _sanitize_inteface_config(iface_config)
    return config


class Config:
    """A NetplanConfig represents the network config for a system.

    Call parse_netplan_config() with each piece of yaml config, and then
    call config_for_device to get the config that matches a particular
    network device, if any.
    """

    def __init__(self):
        self.physical_devices = []
        self.virtual_devices = []
        self.config = {}

    def parse_netplan_config(self, config):
        try:
            self.config = config = yaml.safe_load(config)
        except yaml.ReaderError as e:
            log.info("could not parse config: %s", e)
            return
        network = config.get('network')
        if network is None:
            log.info("no 'network' key in config")
            return
        version = network.get("version")
        if version != 2:
            log.info("network has no/unexpected version %s", version)
            return
        for phys_key in 'ethernets', 'wifis':
            for dev, dev_config in network.get(phys_key, {}).items():
                self.physical_devices.append(_PhysicalDevice(dev, dev_config))
        for virt_key in 'bonds', 'vlans':
            for dev, dev_config in network.get(virt_key, {}).items():
                self.virtual_devices.append(_VirtualDevice(dev, dev_config))

    def config_for_device(self, link):
        if link.is_virtual:
            for dev in self.virtual_devices:
                if dev.name == link.name:
                    return copy.deepcopy(dev.config)
        else:
            allowed_matches = ('macaddress',)
            match_key = 'match'
            for dev in self.physical_devices:
                if dev.matches_link(link):
                    config = copy.deepcopy(dev.config)
                    if match_key in config:
                        match = {k: v for k, v in config[match_key].items()
                                 if k in allowed_matches}
                        if match:
                            config[match_key] = match
                        else:
                            del config[match_key]
                    return config
        return {}

    def load_from_root(self, root):
        for path in configs_in_root(root):
            try:
                fp = open(path)
            except OSError:
                log.exception("opening %s failed", path)
            with fp:
                self.parse_netplan_config(fp.read())


class _PhysicalDevice:
    def __init__(self, name, config):
        match = config.get('match')
        if match is None:
            self.match_name = name
            self.match_mac = None
            self.match_driver = None
        else:
            self.match_name = match.get('name')
            self.match_mac = match.get('macaddress')
            self.match_driver = match.get('driver')
        self.config = config
        log.debug(
            "config for %s = %s" % (
                name, sanitize_interface_config(self.config)))

    def matches_link(self, link):
        if self.match_name is not None:
            matches_name = fnmatch.fnmatch(link.name, self.match_name)
        else:
            matches_name = True
        if self.match_mac is not None:
            matches_mac = self.match_mac == link.hwaddr
        else:
            matches_mac = True
        if self.match_driver is not None:
            matches_driver = self.match_driver == link.driver
        else:
            matches_driver = True
        return matches_name and matches_mac and matches_driver


class _VirtualDevice:
    def __init__(self, name, config):
        self.name = name
        self.config = config
        log.debug(
            "config for %s = %s" % (
                name, sanitize_interface_config(self.config)))


def configs_in_root(root, masked=False):
    """Return a list of all netplan configs under root.

    The list is ordered in increasing precedence.
    @param masked: if True, include config paths that are masked
                   by the same basename in a different directory."""
    if not os.path.isabs(root):
        root = os.path.abspath(root)
    wildcard = "*.yaml"
    dirs = {"lib": "0", "etc": "1", "run": "2"}
    rootlen = len(root)

    paths = []
    for d in dirs:
        paths.extend(glob.glob(os.path.join(root, d, "netplan", wildcard)))

    def mykey(path):
        """returned key is basename + string-precidence based on dir."""
        bname = os.path.basename(path)
        bdir = path[rootlen + 1]
        bdir = bdir[:bdir.find(os.path.sep)]
        return "%s/%s" % (bname, bdir)

    if not masked:
        paths = {os.path.basename(p): p for p in paths}.values()
    return sorted(paths, key=mykey)
