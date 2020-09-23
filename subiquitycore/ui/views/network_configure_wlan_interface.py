import logging

from urwid import (
    BoxAdapter,
    connect_signal,
    LineBox,
    Text,
    )

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
    'subiquitycore.network.network_configure_wlan_interface')


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
    def __init__(self, parent, device):
        self.parent = parent
        self.device = device
        title = _("Network interface {nic} WIFI configuration").format(
            nic=device.name)

        self.form = WLANForm()

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        ssid, psk = self.device.configured_ssid
        if ssid:
            self.form.ssid.value = ssid
        if psk:
            self.form.psk.value = psk

        self.ssid_row = self.form.ssid._table
        self.psk_row = self.form.psk._table
        self.ssid_row.bind(self.psk_row)

        self.inputs = Pile(self._build_iface_inputs())

        self.error = Text("")
        widgets = [
            self.inputs,
            Padding.center_79(Color.info_error(self.error)),
            self.form.buttons,
            ]
        super().__init__(title, widgets, 0, 0)

    def show_ssid_list(self, sender):
        self.parent.show_overlay(
            NetworkList(
                self, self.device.info.wlan['visible_ssids']), width=60)

    def start_scan(self, sender):
        fp = self.inputs.focus_position - 1
        while not self.inputs.contents[fp][0].selectable():
            fp -= 1
        self.inputs.focus_position = fp
        try:
            self.parent.controller.start_scan(self.device)
        except RuntimeError as r:
            log.exception("start_scan failed")
            self.error.set_text("%s" % (r,))

    def _build_iface_inputs(self):
        if len(self.device.info.wlan['visible_ssids']) > 0:
            networks_btn = menu_btn("Choose a visible network",
                                    on_press=self.show_ssid_list)
        else:
            networks_btn = disabled(menu_btn("No visible networks"))

        if not self.device.info.wlan['scan_state']:
            scan_btn = menu_btn("Scan for networks", on_press=self.start_scan)
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

    def refresh_model_inputs(self):
        try:
            self.device = self.parent.model.get_netdev_by_name(
                self.device.name)
        except KeyError:
            # The interface is gone
            self.parent.remove_overlay()
            return
        self.inputs.contents = [(obj, ('pack', None))
                                for obj in self._build_iface_inputs()]

    def done(self, sender):
        if self.device.configured_ssid[0] is None and self.form.ssid.value:
            # Turn DHCP4 on by default when specifying an SSID for
            # the first time...
            self.device.config['dhcp4'] = True
        if self.form.ssid.value:
            ssid = self.form.ssid.value
        else:
            ssid = None
        if self.form.psk.value:
            psk = self.form.psk.value
        else:
            psk = None
        self.device.set_ssid_psk(ssid, psk)
        self.parent.update_link(self.device)
        self.parent.remove_overlay()
        self.parent.controller.apply_config()

    def cancel(self, sender=None):
        self.parent.remove_overlay()
