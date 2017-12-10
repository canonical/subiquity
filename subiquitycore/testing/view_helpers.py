import re

import urwid

def find_with_pred(w, pred):
    def _walk(w):
        if pred(w):
            return w
        if hasattr(w, '_wrapped_widget'):
            return _walk(w._wrapped_widget)
        if hasattr(w, 'original_widget'):
            return _walk(w.original_widget)
        if isinstance(w, urwid.ListBox):
            for w in w.body:
                r = _walk(w)
                if r:
                    return r
        elif hasattr(w, 'contents'):
            contents = w.contents
            for w, _ in contents:
                r = _walk(w)
                if r:
                    return r
    return _walk(w)

def find_button_matching(w, pat):
    def pred(w):
        return isinstance(w, urwid.Button) and re.match(pat, w.label)
    return find_with_pred(w, pred)

def click(but):
    but._emit('click')

def keypress(w, key, size=(30, 1)):
    w.keypress(size, key)

def get_focus_path(w):
    path = []
    while True:
        path.append(w)
        if isinstance(w, urwid.ListBox) and w.set_focus_pending == "first selectable":
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
        getattr(form, k).value = v
