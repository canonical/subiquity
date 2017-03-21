from urwid import (
    BoxAdapter,
    Button,
    connect_signal,
    LineBox,
    Text,
    WidgetWrap,
    )
from subiquitycore.view import BaseView
from subiquitycore.ui.buttons import cancel_btn, menu_btn
from subiquitycore.ui.container import Columns, ListBox, Pile
from subiquitycore.ui.form import Form, PasswordField, StringField
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
        self.parent.form.ssid.value = sender.label
        self.parent.remove_overlay()

    def do_cancel(self, sender):
        self.parent.remove_overlay()


class WLANForm(Form):

    ssid = StringField(caption="Network Name:")
    psk = PasswordField(caption="Password:")

    def validate_psk(self):
        psk = self.psk.value
        if len(psk) == 0:
            return
        elif len(psk) < 8:
            return "Password must be at least 8 characters long if present"
        elif len(psk) > 63:
            return "Password must be less than 63 characters long"

class NetworkConfigureWLANView(BaseView):
    def __init__(self, model, controller, name):
        self.model = model
        self.controller = controller
        self.dev = self.model.get_netdev_by_name(name)

        self.form = WLANForm()

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        if self.dev.configured_ssid is not None:
            self.form.ssid.value = self.dev.configured_ssid
        if self.dev.configured_wifi_psk is not None:
            self.form.psk.value = self.dev.configured_wifi_psk

        self.ssid_row = self.form.ssid.as_row(self, self.form.longest_caption)
        self.psk_row = self.form.psk.as_row(self, self.form.longest_caption)

        self.inputs = Pile(self._build_iface_inputs())

        self.error = Text("")
        self.body = [
            Padding.center_79(self.inputs),
            Padding.line_break(""),
            Padding.center_79(Color.info_error(self.error)),
            Padding.line_break(""),
            Padding.fixed_10(Pile([self.form.done_btn, self.form.cancel_btn])),
        ]
        self.orig_w = None
        super().__init__(ListBox(self.body))

    def keypress(self, size, key):
        if key == 'esc':
            if self.orig_w is not None:
                self.remove_overlay()
                return
        return super().keypress(size, key)

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
            self.ssid_row,
            Padding.fixed_30(networks_btn),
            Padding.fixed_30(scan_btn),
            self.psk_row,
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

    def done(self, sender):
        if self.dev.configured_ssid is None and self.form.ssid.value:
            # Turn DHCP4 on by default when specifying an SSID for the first time...
            self.dev.dhcp4 = True
        if self.form.ssid.value:
            ssid = self.form.ssid.value
        else:
            ssid = None
        if self.form.psk.value:
            psk = self.form.psk.value
        else:
            psk = None
        self.dev.set_ssid_psk(ssid, psk)
        self.controller.prev_view()

    def cancel(self, sender):
        self.controller.prev_view()
