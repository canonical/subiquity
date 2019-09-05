from unittest import TestCase

from urwid import Text

from subiquitycore.testing import view_helpers
from subiquitycore.view import BaseView

from subiquity.core import Subiquity


class FakeOpts:
    bootloader = None
    machine_config = None
    dry_run = True
    answers = None
    screens = None
    snaps_from_examples = True


class SubiquityTests(TestCase):

    def make_app(self, view=None):
        app = Subiquity(FakeOpts(), '')

        if view is None:
            view = BaseView(Text(""))
        app.ui.set_body(view)

        return app

    def test_global_extra(self):
        app = self.make_app()

        app.ui._w.base_widget.focus_position = 2

        self.assertTrue(app.ui.right_icon.selectable())

        overlay = app.show_global_extra()

        for w in view_helpers.get_focus_path(app.ui._w):
            if w is overlay:
                break
        else:
            self.fail("help dialog not focused")

        self.assertFalse(app.ui.right_icon.selectable())

        app.ui.body.remove_overlay()
        self.assertEqual(app.ui._w.base_widget.focus_position, 2)
        self.assertTrue(app.ui.right_icon.selectable())

    def test_global_extra_keys(self):
        app = self.make_app()
        app.unhandled_input('f1')
        self.assertTrue(app.showing_global_extra)
        app = self.make_app()
        app.unhandled_input('ctrl h')
        self.assertTrue(app.showing_global_extra)
