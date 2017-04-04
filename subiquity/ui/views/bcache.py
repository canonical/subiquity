# Copyright 2015 Canonical, Ltd.
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

import logging
from urwid import Text

from subiquitycore.view import BaseView
from subiquitycore.ui.buttons import cancel_btn, done_btn
from subiquitycore.ui.container import ListBox, Pile
from subiquitycore.ui.interactive import Selector
from subiquitycore.ui.utils import Color, Padding

from subiquity.models.filesystem import humanize_size

log = logging.getLogger('subiquity.ui.bcache')


class BcacheView(BaseView):
    def __init__(self, model, signal):
        self.model = model
        self.signal = signal
        self.selected_disks = {
            'CACHE': None,
            'BACKING': None,
        }
        body = [
            Padding.center_50(self._build_disk_selection(section='CACHE')),
            Padding.line_break(""),
            Padding.center_50(self._build_disk_selection(section='BACKING')),
            Padding.line_break(""),
            Padding.fixed_10(self._build_buttons())
        ]
        super().__init__(ListBox(body))

    @property
    def cache_disk(self):
        selector = self.selected_disks['CACHE']
        if selector:
            return selector.value
        return selector

    @property
    def backing_disk(self):
        selector = self.selected_disks['BACKING']
        if selector:
            return selector.value
        return selector

    def _build_disk_selection(self, section):
        log.debug('bcache: _build_disk_selection, section:' + section)
        items = [
            Text(section + " DISK SELECTION")
        ]

        avail_devs = self._get_available_devs(section)
        if len(avail_devs) == 0:
            return items.append(
                [Color.info_minor(Text("No available disks."))])

        selector = Selector(avail_devs)
        self.selected_disks[section] = selector
        items.append(Color.string_input(selector))

        return Pile(items)

    def _get_available_devs(self, section):
        devs = []

        # bcache can use empty whole disks, or empty partitions
        avail_disks = self.model.get_empty_disk_names()
        avail_parts = self.model.get_empty_partition_names()
        input_disks = avail_disks + avail_parts
        if section == 'CACHE':
            input_disks += self.model.get_bcache_cachedevs()

        # filter out:
        #  currently selected cache or backing disk
        #  any bcache devices
        bcache_names = list(self.model.bcache_devices.keys())
        selected_disks = [self.backing_disk, self.cache_disk]
        filter_disks = bcache_names + selected_disks

        avail_devs = sorted([dev for dev in input_disks
                             if dev not in filter_disks])

        for dname in avail_devs:
            device = self.model.get_disk(dname)
            if device.path != dname:
                # we've got a partition
                bcachedev = device.get_partition(dname)
            else:
                bcachedev = device

            disk_sz = humanize_size(bcachedev.size)
            disk_string = "{}     {},     {}".format(dname,
                                                     disk_sz,
                                                     device.model)
            log.debug('bcache: disk_string={}'.format(disk_string))
            devs.append(disk_string)

        return devs

    def _build_buttons(self):
        log.debug('bcache: _build_buttons')
        cancel = cancel_btn(on_press=self.cancel)
        done = done_btn(on_press=self.done)

        buttons = [
            Color.button(done),
            Color.button(cancel)
        ]
        return Pile(buttons)

    def done(self, result):
        result = {
            'backing_device': self.backing_disk,
            'cache_device': self.cache_disk,
        }
        if not result['backing_device']:
            log.debug('Must select a backing device to create a bcache dev')
            return
        if not result['cache_device']:
            log.debug('Must select a caching device to create a bcache dev')
            return
        if result['backing_device'] == result['cache_device']:
            log.debug('Cannot select the same device for backing and cache')
            return

        log.debug('bcache_done: result = {}'.format(result))
        self.model.add_bcache_device(result)

        self.signal.prev_signal()

    def cancel(self, button):
        log.debug('bcache: button_cancel')
        self.signal.prev_signal()
