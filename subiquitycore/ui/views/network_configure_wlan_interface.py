from urwid import Text, Pile, ListBox, Columns, Overlay, WidgetWrap, LineBox, Button, BoxAdapter
from subiquitycore.view import BaseView
from subiquitycore.ui.buttons import cancel_btn, done_btn, menu_btn
from subiquitycore.ui.interactive import PasswordEditor, StringEditor
from subiquitycore.ui.utils import Color, Padding
import logging

log = logging.getLogger('subiquitycore.network.network_configure_wlan_interface')


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

    def _build_iface_inputs(self):
        col = [
            Padding.center_79(Color.info_minor(Text("Only open or WPA2/PSK networks are supported at this time."))),
            Padding.line_break(""),
            Columns(
                [
                    ("weight", 0.2, Text("Network name:")),
                    ("weight", 0.3,
                     Color.string_input(self.ssid_input,
                                        focus_map="string_input focus")),
                ], dividechars=2
            ),
            Columns(
                [
                    ("weight", 0.2, Text("Password:")),
                    ("weight", 0.3,
                     Color.string_input(self.psk_input,
                                        focus_map="string_input focus")),
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
        cancel = Color.button(cancel_btn(on_press=self.cancel),
                              focus_map='button focus')
        done = Color.button(done_btn(on_press=self.done),
                            focus_map='button focus')

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
