# Copyright 2020 Canonical, Ltd.
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


class ControllerSet:

    def __init__(self, controllers_mod, names, init_args=()):
        self.controllers_mod = controllers_mod
        self.controller_names = names[:]
        self.init_args = init_args
        self.index = -1
        self.instances = []

    def _get_controller_class(self, name):
        cls_name = name+"Controller"
        return getattr(self.controllers_mod, cls_name)

    def load(self, name):
        self.controller_names.remove(name)
        klass = self._get_controller_class(name)
        if hasattr(self, name):
            c = 1
            for instance in self.instances:
                if isinstance(instance, klass):
                    c += 1
            rep_cls = self._get_controller_class("Repeated")
            inst = rep_cls(getattr(self, name), c)
            name = inst.name
        else:
            inst = klass(*self.init_args)
        setattr(self, name, inst)
        self.instances.append(inst)

    def load_all(self):
        while self.controller_names:
            self.load(self.controller_names[0])

    @property
    def cur(self):
        if self.out_of_bounds():
            return None
        return self.instances[self.index]

    def out_of_bounds(self):
        return self.index < 0 or self.index >= len(self.instances)
