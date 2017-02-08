from urwid import Text, Overlay, WidgetWrap, LineBox, Button, BoxAdapter
from subiquitycore.view import BaseView
from subiquitycore.ui.buttons import cancel_btn, done_btn, menu_btn
from subiquitycore.ui.container import Columns, ListBox, Pile
from subiquitycore.ui.interactive import PasswordEditor, StringEditor
from subiquitycore.ui.utils import Color, Padding
import logging

log = logging.getLogger('subiquitycore.network.network_configure_wlan_interface')

class NetworkList(WidgetWrap):

    def __init__(self, parent, ssids):
        self.parent = parent
        button = cancel_btn(on_press=self.do_cancel)
        ssid_list = [
            Color.menu_button(
                Button(label=ssid, on_press=self.do_network))
            for ssid in ssids]
        p = Pile([BoxAdapter(ListBox(ssid_list), height=10), Padding.fixed_10(button)])
        box = LineBox(p, title="Select a network")
        super().__init__(box)

    def do_network(self, sender):
        self.parent.ssid_input.value = sender.label
        self.parent.remove_overlay()

    def do_cancel(self, sender):
        self.parent.remove_overlay()


class NetworkConfigureWLANView(BaseView):
    def __init__(self, model, controller, name):
        self.model = model
        self.controller = controller
        self.dev = self.model.get_netdev_by_name(name)
        self.ssid_input = StringEditor(caption="")
        if self.dev.configured_ssid is not None:
            self.ssid_input.value = self.dev.configured_ssid
        self.psk_input = PasswordEditor(caption="")
        if self.dev.configured_wifi_psk is not None:
            self.psk_input.value = self.dev.configured_wifi_psk
        self.inputs = Pile(self._build_iface_inputs())
        self.error = Text("")
        self.body = [
            Padding.center_79(self.inputs),
            Padding.line_break(""),
            Padding.center_79(Color.info_error(self.error)),
            Padding.line_break(""),
            Padding.fixed_10(self._build_buttons())
        ]
        self.orig_w = None
        super().__init__(ListBox(self.body))

    def keypress(self, size, key):
        if key == 'esc':
            if self.orig_w is not None:
                self.remove_overlay()
                return
        return super().keypress(size, key)

    def show_overlay(self, overlay_widget):
        self.orig_w = self._w
        self._w = Overlay(top_w=overlay_widget,
                          bottom_w=self._w,
                          align='center',
                          width=('relative', 60),
                          min_width=80,
                          valign='middle',
                          height='pack')

    def remove_overlay(self):
        self._w = self.orig_w
        self.orig_w = None

    def show_ssid_list(self, sender):
        self.show_overlay(NetworkList(self, self.dev.actual_ssids))

    def start_scan(self, sender):
        self.keypress((0,0), 'up')
        try:
            self.controller.start_scan(self.dev)
        except RuntimeError as r:
            log.exception("start_scan failed")
            self.error.set_text("%s" % (r,))

    def _build_iface_inputs(self):
        if len(self.dev.actual_ssids) > 0:
            networks_btn = Color.menu_button(
                menu_btn("Choose a visible network", on_press=self.show_ssid_list))
        else:
            networks_btn = Color.info_minor(Columns(
                [
                    ('fixed', 1, Text("")),
                    Text("No visible networks"),
                    ('fixed', 1, Text(">"))
                ], dividechars=1))
        if not self.dev.scan_state:
            scan_btn = Color.menu_button(
                menu_btn("Scan for networks", on_press=self.start_scan))
        else:
            scan_btn = Color.info_minor(Columns(
                [
                    ('fixed', 1, Text("")),
                    Text("Scanning for networks"),
                    ('fixed', 1, Text(">"))
                ], dividechars=1))

        col = [
            Padding.center_79(Color.info_minor(Text("Only open or WPA2/PSK networks are supported at this time."))),
            Padding.line_break(""),
            Columns(
                [
                    ("weight", 0.2, Text("Network name:")),
                    ("weight", 0.3, Color.string_input(self.ssid_input)),
                ], dividechars=2
            ),
            Columns(
                [
                    ("weight", 1.0,
                     Padding.fixed_30(networks_btn)),
                ]
            ),
            Columns(
                [
                    ("weight", 1.0,
                     Padding.fixed_30(scan_btn)),
                ]
            ),
            Columns(
                [
                    ("weight", 0.2, Text("Password:")),
                    ("weight", 0.3,
                     Color.string_input(self.psk_input)),
                ], dividechars=2
            ),
        ]
        return col

    def refresh_model_inputs(self):
        try:
            self.dev = self.model.get_netdev_by_name(self.dev.name)
        except KeyError:
            # The interface is gone
            self.controller.prev_view()
            self.controller.prev_view()
            return
        self.inputs.contents = [ (obj, ('pack', None)) for obj in self._build_iface_inputs() ]

    def _build_buttons(self):
        cancel = Color.button(cancel_btn(on_press=self.cancel))
        done = Color.button(done_btn(on_press=self.done))

        buttons = [done, cancel]
        return Pile(buttons, focus_item=done)

    def done(self, btn):
        if self.dev.configured_ssid is None and self.ssid_input.value:
            # Turn DHCP4 on by default when specifying an SSID for the first time...
            self.dev.dhcp4 = True
        if self.ssid_input.value:
            ssid = self.ssid_input.value
        else:
            ssid = None
        if self.psk_input.value:
            psk = self.psk_input.value
        else:
            psk = None
        self.dev.set_ssid_psk(ssid, psk)
        self.controller.prev_view()

    def cancel(self, btn):
        self.controller.prev_view()
