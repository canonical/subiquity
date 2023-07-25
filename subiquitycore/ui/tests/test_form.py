# Copyright 2022 Canonical, Ltd.
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

from unittest import TestCase

from subiquitycore.ui.form import Form, StringField, SubForm, SubFormField


class TestForm(TestCase):
    def test_has_validation_error(self):
        """Make sure Form.has_validation_form() returns:
        * True if any field is in error
        * False otherwise."""

        class SampleForm(Form):
            field1 = StringField("FieldOne", help="")
            field2 = StringField("FieldTwo", help="")

        form = SampleForm()

        form.field1.in_error = False
        form.field2.in_error = False
        self.assertFalse(form.has_validation_error())

        form.field1.in_error = True
        form.field2.in_error = True
        self.assertTrue(form.has_validation_error())

        form.field1.in_error = True
        form.field2.in_error = False
        self.assertTrue(form.has_validation_error())

    def test_has_validation_error_with_subform(self):
        """Make sure Form.has_validation_form() is affected by fields from
        child forms (only if the child form is enabled)."""

        class SampleSubForm(SubForm):
            field1 = StringField("FieldString", help="")

        class SampleForm(Form):
            field1 = StringField("FieldString", help="")
            sample_subform = SubFormField(SampleSubForm, "", help="")

        form = SampleForm()
        subform = form.sample_subform.widget.form

        form.field1.in_error = False
        subform.field1.in_error = False
        self.assertFalse(form.has_validation_error())

        form.field1.in_error = True
        subform.field1.in_error = False
        self.assertTrue(form.has_validation_error())

        form.field1.in_error = False
        subform.field1.in_error = True
        self.assertTrue(form.has_validation_error())

        form.field1.in_error = True
        subform.field1.in_error = True
        self.assertTrue(form.has_validation_error())

        # Make sure fields in disabled subforms are ignored.
        form.field1.in_error = False
        subform.field1.in_error = True
        form.sample_subform.enabled = False
        self.assertFalse(form.has_validation_error())

    def test_has_validation_error_with_subsubform(self):
        """Make sure enabling/disabling parent forms also acts as if sub forms
        are disabled."""

        class SampleSubSubForm(SubForm):
            field1 = StringField("SampleString", help="")

        class SampleSubForm(SubForm):
            sample_subform = SubFormField(SampleSubSubForm, "", help="")

        class SampleForm(Form):
            sample_subform = SubFormField(SampleSubForm, "", help="")

        form = SampleForm()
        subform = form.sample_subform.widget.form
        subsubform = subform.sample_subform.widget.form

        subsubform.field1.in_error = True
        self.assertTrue(form.has_validation_error())

        # If subsubform is disabled, it should be ignored.
        subsubform.field1.in_error = True
        subform.sample_subform.enabled = False
        self.assertFalse(form.has_validation_error())

        # If subform is disabled, it should also be ignored.
        subsubform.field1.in_error = True
        subform.sample_subform.enabled = True
        form.sample_subform.enabled = False
        self.assertFalse(form.has_validation_error())

    def test_done_button_auto_toggle(self):
        """Make sure calling validated() enables or disables the Done button."""

        class SampleForm(Form):
            field1 = StringField("SampleString", help="")

        form = SampleForm()
        done_button = form.buttons.base_widget.contents[0][0]

        form.field1.in_error = False
        form.validated()
        self.assertTrue(done_button.enabled)

        form.field1.in_error = True
        form.validated()
        self.assertFalse(done_button.enabled)

    def test_subform_validated_propagates(self):
        """Make sure calling validated() in a subform affects the Done button
        in the parent form."""

        class SampleSubForm(SubForm):
            field1 = StringField("SampleString", help="")

        class SampleForm(Form):
            sample_subform = SubFormField(SampleSubForm, "", help="")

        form = SampleForm()
        subform = form.sample_subform.widget.form
        done_button = form.buttons.base_widget.contents[0][0]

        subform.field1.in_error = False
        subform.validated()
        self.assertTrue(done_button.enabled)

        subform.field1.in_error = True
        subform.validated()
        self.assertFalse(done_button.enabled)
