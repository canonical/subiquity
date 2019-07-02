import re
import urwid

from subiquitycore.ui.stretchy import StretchyOverlay


def find_with_pred(w, pred, return_path=False):
    def _walk(w, path):
        if not isinstance(w, urwid.Widget):
            raise RuntimeError(
                "_walk walked to non-widget %r via %r" % (w, path))
        if pred(w):
            return w, path
        if hasattr(w, '_wrapped_widget'):
            return _walk(w._wrapped_widget, (w,) + path)
        if hasattr(w, 'original_widget'):
            return _walk(w.original_widget, (w,) + path)
        if isinstance(w, urwid.ListBox):
            for w in w.body:
                r, p = _walk(w, (w,) + path)
                if r:
                    return r, p
        elif isinstance(w, urwid.Frame):
            for w, _ in w.contents.values():
                r, p = _walk(w, (w,) + path)
                if r:
                    return r, p
        elif hasattr(w, 'contents'):
            contents = w.contents
            for w, _ in contents:
                r, p = _walk(w, (w,) + path)
                if r:
                    return r, p
        elif isinstance(w, StretchyOverlay):
            r, p = _walk(w.top_w, (w,) + path)
            if r:
                return r, p
        return None, None
    r, p = _walk(w, ())
    if return_path:
        return r, p
    else:
        return r


def find_button_matching(w, pat, return_path=False):
    def pred(w):
        return isinstance(w, urwid.Button) and re.match(pat, w.label)
    return find_with_pred(w, pred, return_path)


def click(but):
    but._emit('click')


def keypress(w, key, size=(30, 1)):
    w.keypress(size, key)


def get_focus_path(w):
    path = []
    while True:
        path.append(w)
        if isinstance(w, urwid.ListBox) and (w.set_focus_pending ==
                                             "first selectable"):
            for w2 in w.body:
                if w2.selectable():
                    w = w2
                    break
            else:
                break
        if w.focus is not None:
            w = w.focus
        elif hasattr(w, '_wrapped_widget'):
            w = w._wrapped_widget
        elif hasattr(w, 'original_widget'):
            w = w.original_widget
        else:
            break
    return path


def enter_data(form, data):
    for k, v in data.items():
        bf = getattr(form, k)
        assert bf.enabled, "%s is not enabled" % (k,)
        bf.value = v
