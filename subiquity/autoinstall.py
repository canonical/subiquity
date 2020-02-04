# Copyright 2019 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import yaml

from curtin.config import merge_config


def merge_autoinstall_configs(source_paths, target_path):
    config = {}
    for path in source_paths:
        with open(path) as fp:
            c = yaml.safe_load(fp)
        merge_config(config, c)
    with open(target_path, 'w') as fp:
        yaml.dump(config, fp)
