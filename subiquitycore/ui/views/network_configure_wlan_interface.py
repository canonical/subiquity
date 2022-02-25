import logging

from urwid import (
    BoxAdapter,
    connect_signal,
    LineBox,
    Text,
    )

from subiquitycore.models.network import WLANConfig
from subiquitycore.ui.buttons import cancel_btn, menu_btn
from subiquitycore.ui.container import (
    ListBox,
    Pile,
    WidgetWrap,
    )
from subiquitycore.ui.form import Form, PasswordField, StringField
from subiquitycore.ui.stretchy import Stretchy
from subiquitycore.ui.utils import (
    Color,
    disabled,
    Padding,
    )

log = logging.getLogger(
    'subiquitycore.ui.views.network_configure_wlan_interface')


class NetworkList(WidgetWrap):

    def __init__(self, parent, ssids):
        self.parent = parent
        button = cancel_btn(_("Cancel"), on_press=self.do_cancel)
        ssid_list = [menu_btn(label=ssid, on_press=self.do_network)
                     for ssid in ssids if ssid]
        p = Pile([BoxAdapter(ListBox(ssid_list), height=10),
                  Padding.fixed_10(button)])
        box = LineBox(p, title=_("Select a network"))
        super().__init__(box)

    def do_network(self, sender):
        self.parent.form.ssid.value = sender.label
        self.parent.parent.remove_overlay()

    def do_cancel(self, sender):
        self.parent.parent.remove_overlay()


class WLANForm(Form):

    ok_label = _("Save")

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


class NetworkConfigureWLANStretchy(Stretchy):
    def __init__(self, parent, dev_info):
        self.parent = parent
        self.dev_info = dev_info
        title = _("Network interface {nic} WIFI configuration").format(
            nic=dev_info.name)

        self.form = WLANForm()

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        if self.dev_info.wlan.config.ssid:
            self.form.ssid.value = self.dev_info.wlan.config.ssid
        if self.dev_info.wlan.config.psk:
            self.form.psk.value = self.dev_info.wlan.config.psk

        self.ssid_row = self.form.ssid._table
        self.psk_row = self.form.psk._table
        self.ssid_row.bind(self.psk_row)

        self.error = Text("")

        self.inputs = Pile(self._build_iface_inputs())

        widgets = [
            self.inputs,
            Padding.center_79(Color.info_error(self.error)),
            self.form.buttons,
            ]
        super().__init__(title, widgets, 0, 0)

    def show_ssid_list(self, sender):
        self.parent.show_overlay(
            NetworkList(self, self.dev_info.wlan.visible_ssids),
            width=60)

    def start_scan(self, sender):
        fp = self.inputs.focus_position - 1
        while not self.inputs.contents[fp][0].selectable():
            fp -= 1
        self.inputs.focus_position = fp
        self.parent.controller.start_scan(self.dev_info.name)

    def _build_iface_inputs(self):
        visible_ssids = self.dev_info.wlan.visible_ssids
        if len(visible_ssids) > 0:
            networks_btn = menu_btn("Choose a visible network",
                                    on_press=self.show_ssid_list)
        else:
            networks_btn = disabled(menu_btn("No visible networks"))

        scan_state = self.dev_info.wlan.scan_state
        if not scan_state:
            scan_btn = menu_btn("Scan for networks", on_press=self.start_scan)
        elif scan_state.startswith('error'):
            self.error.set_text('scan failed: %s' % (scan_state,))
            scan_btn = disabled(menu_btn("Scanning for networks failed"))
        else:
            scan_btn = disabled(menu_btn("Scanning for networks"))

        warning = (
            "Only open or WPA2/PSK networks are supported at this time.")
        col = [
            Text(warning),
            Text(""),
            self.ssid_row,
            Text(""),
            Padding.fixed_32(networks_btn),
            Padding.fixed_32(scan_btn),
            Text(""),
            self.psk_row,
        ]
        return col

    def update_link(self, dev_info):
        if dev_info.name != self.dev_info.name:
            return
        self.dev_info = dev_info
        self.inputs.contents = [(obj, ('pack', None))
                                for obj in self._build_iface_inputs()]

    def done(self, sender):
        if self.form.ssid.value:
            ssid = self.form.ssid.value
        else:
            ssid = None
        if self.form.psk.value:
            psk = self.form.psk.value
        else:
            psk = None
        self.parent.controller.set_wlan(
            self.dev_info.name, WLANConfig(ssid=ssid, psk=psk))
        self.parent.update_link(self.dev_info)
        self.parent.remove_overlay()

    def cancel(self, sender=None):
        self.parent.remove_overlay()
