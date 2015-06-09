# Copyright 2015 Canonical, Ltd.

""" Base Frame Widget """

from urwid import Frame, WidgetWrap


class Base(WidgetWrap):
    def __init__(self, header, body, footer):
        self.frame = Frame(body,
                           header,
                           footer)
        super().__init__(self.frame)
