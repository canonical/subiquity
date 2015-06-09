# Copyright 2015 Canonical, Ltd.

from urwid import WidgetWrap, AttrWrap, Pile, Text, Columns


class Header(WidgetWrap):
    """ Header Widget

    This widget uses the style key `frame_header`

    :param str title: Title of Header
    :returns: Header()
    """
    def __init__(self, title="Ubuntu Server Installer"):
        title = title
        title_widget = AttrWrap(Text(title), "frame_header")
        pile = Pile([title_widget])
        super().__init__(Columns(pile))


class Footer(WidgetWrap):
    """ Footer widget

    Style key: `frame_footer`

    """
    def __init__(self):
        status = Pile([Text("")])
        super().__init__(Columns(status))


class Body(WidgetWrap):
    """ Body widget
    """
    def __init__(self):
        super().__init__(Text("Welcome to the Server Installation"))
