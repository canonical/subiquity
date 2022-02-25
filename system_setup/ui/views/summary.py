""" Summary

Summary provides user with the summary of all the current settings.

"""

import logging

from subiquitycore.ui.utils import button_pile, screen
from subiquitycore.view import BaseView
from subiquitycore.ui.form import Toggleable
from subiquitycore.ui.buttons import (
    cancel_btn,
    ok_btn,
    )
from subiquitycore.ui.width import widget_width
from subiquity.common.types import ApplicationState

from subiquitycore.ui.container import ListBox
from urwid import Text

log = logging.getLogger("system_setup.ui.views.summary")


class SummaryView(BaseView):
    title = _("Setup Complete")

    def __init__(self, controller, real_name):
        self.controller = controller
        completed = _("You have completed the setup!\n\n"
                      "All settings will take effect after next "
                      "restart of Ubuntu.")
        if real_name != '':
            completed = _("Hi {real_name},\n\n"
                          "You have completed the setup!\n\n"
                          "It is suggested to run the following commands"
                          " to update your Ubuntu to the latest version:"
                          "\n\n\n"
                          "  $ sudo apt update\n  $ sudo apt upgrade\n\n\n"
                          "All settings will take effect after next "
                          "restart of Ubuntu.").format(real_name=real_name)
        self.completed = completed

        self.reboot_btn = Toggleable(ok_btn(
            _("Reboot Now"), on_press=self.reboot))
        self.view_error_btn = cancel_btn(
            _("View error report"), on_press=self.view_error)

        self.event_buttons = button_pile([])
        self.body = ListBox([Text(_("Applying changes…"))])
        super().__init__(
            screen(
                rows=self.body,
                buttons=self.event_buttons,
                focus_buttons=True,
                excerpt=None,
            )
        )

    def update_for_state(self, state):
        btns = []
        if state == ApplicationState.DONE:
            btns = [self.reboot_btn]
            self.body.base_widget.body = [Text(self.completed)]
        elif state == ApplicationState.ERROR:
            self.title = _('An error occurred during installation')
            self.reboot_btn.base_widget.set_label(_("Reboot Now"))
            self.reboot_btn.enabled = True
            btns = [
                self.view_error_btn,
                self.reboot_btn,
                ]
        if self.controller.showing:
            self.controller.app.ui.set_header(self.title)
        self._set_buttons(btns)

    def reboot(self, btn):
        log.debug('reboot clicked')
        self.reboot_btn.base_widget.set_label(_("Rebooting..."))
        self.reboot_btn.enabled = False
        self.event_buttons.original_widget._select_first_selectable()
        self.controller.click_reboot()
        self._set_button_width()

    def view_error(self, btn):
        self.controller.app.show_error_report(self.controller.crash_report_ref)

    def _set_button_width(self):
        w = 14
        for b, o in self.event_buttons.original_widget.contents:
            w = max(widget_width(b), w)
        self.event_buttons.width = self.event_buttons.min_width = w

    def _set_buttons(self, buttons):
        p = self.event_buttons.original_widget
        p.contents[:] = [(b, p.options('pack')) for b in buttons]
        self._set_button_width()
