# subiquity design notes

## UI

### basic ground rules:

1. Subiquity is entirely usable by pressing up, down, space (or return) and the
   occasional bit of typing.

2. The UI never blocks.  If something takes more than about 0.1s, it is done
   in the background, possibly with some kind of indication in the UI and the
   ability to cancel if appropriate.  (We should consider making sure that if
   we pop up a progress dialog while something happens -- e.g. applying
   keyboard configuration, which the user just has to wait for until going on
   to the next screen -- that the dialog appears for at least, say, 0.5s to
   avoid flickering the UI).

3. General UX principles that it is worth keeping in mind:

    1. Prevent invalid use if that makes sense (e.g. unix usernames can never
       contain spaces, so you simply can't enter spaces in that box)

    2. When rejecting input, be clear about that to the user and explain what
       they need to do differently (e.g. when you do try to put a space in a
       unix username, a message appears explaining which characters are valid).

    3. Make the common case as easy as possible by doing things like thinking
       about which widget should be highlighted when a screen is first shown.

4. Subiquity is functional in an 80x24 terminal.  It doesn't matter if it falls
   apart in a smaller terminal and obviously you can get more information on a
   larger terminal at once, but it needs to work in 80x24.

### urwid specific ranting

subiquity is built using the [urwid](http://urwid.org/) console user interface
library for Python.  urwid is mostly fine but has some design decisions that
have meant that we're sort of slowly re-implementing pieces of it.

The main one of these is that in urwid, widgets do not have a size; they
inherit it from their parent widget.  While this is unavoidable for the "outer"
widgets (subiquity does not get to decide the size of the console it runs in!)
I don't think it leads to a good appearance for things like stacked columns of
buttons, which we want to fit to label length (and label length depends on
which language it is being used in!). There is a similar tension around having
scroll bars that are only shown when needed (scroll bars should only be shown
when the contained widget "wants" to be taller than the space available for
it).

subiquity has a few generic facilities for handling these:

 * The `subiquitycore.ui.containers` module defines a `ListBox` class that
   automatically handles scroll bars. It is used everywhere instead of urwid's
   `ListBox` class (it does not support lazy construction of widgets like
   urwid's does).

 * The `subiquitycore.ui.stretchy` module defines classes for creating modal
   dialogs out of stacks of widgets that fit to their content (and let you say
   which widget to scroll if the content is too tall to fit on the screen).

 * The `subiquitycore.ui.width` module defines a `widget_width` function, which
   knows how wide a widget "wants" to be (as above, this isn't a concept urwid
   comes with).

 * The `subiquitycore.ui.table` module defines classes for creating Tables that
   act a little like `<table>` elements in HTML.

Subiquity also has replacements for the standard containers that handle tab
cycling (i.e. tab advances to the next element and wraps around to the
beginning when at the end).

urwid can be extremely frustrating to work with, but usually a good UI can be
implemented after sufficient swearing.

### The typical screen

A subiquity screen consists of:

 1. a header
 2. a body area, which usually contains
    1. an excerpt (which explains what this screen is for)
    2. a scrollable content area
    3. a stack of buttons, including "done"/"cancel" buttons for moving between
       screens

The header has a summary line describing the current screen against an "ubuntu
orange" background.

The body area is where most of the action is. It follows a standard pattern
described above, and the `subiquitycore.ui.utils.screen()` function makes it
very easy to follow that pattern.  Many screen have "sub-dialogs" (think:
editing the addresses for a NIC) which can be as large as the whole body area
but are often smaller. The base view class has `show_overlay`/`hide_overlay`
methods for handling these.

### Custom widgets

subiquity defines a few generic widgets that are used in several places.

`Selector` is a bit like an html `<select>` element. Use it to choose one of
several choices, e.g. which filesystem to format a partition with.

`ActionMenu` is a widget that pops up a submenu containing "actions" when
selected. It's used on things like the network screen, which has one
`ActionMenu` per NIC.

`Spinner` is a simple widget that animates to give a visual indication of
progress.

### Forms

`subiquity.ui.form` defines classes for handling forms, somewhat patterned
after Django's forms.  A form defines a sequence of fields and has a way of
turning them into widgets for the UI, provides hooks for validation, handles
initial data, supports enabling and disabling fields, etc.

Forms make it _very_ easy to whip up a screen or dialog quickly. By the time
one has got all the validation working and the cross-linking between the fields
done so that checking _this_ box means _that_ text field gets enabled and all
the other stuff you end up having to do to make a good UI it can all get fairly
complicated, but the ability to start easily makes it well worth it IMHO.

## Code structure

Subiquity follows a model / view / controller sort of approach.

The model is ultimately the config that will be passed to curtin, which is
broken apart into classes for the configuration of the network, the filesystem,
the language, etc, etc.  The full model lives in `subiquity.models.subiquity`
and the submodels live in modules like `subiquitycore.models.network` and
`subiquity.models.keyboard`.

Subiquity presents itself as a series of screens -- Welcome, Keyboard, Network,
etc etc -- as described above.  Each screen is managed by an instance of a
controller class. The controller also manages the relationship between the
outside world and the model and views -- in the network view, it is the
controller that listens to netlink events and calls methods on the model and
view instances in response to, say, a NIC gaining an address.

The views display the model and call methods on the controller to make changes.

Obviously for most screens there is a triple of a model class, controller class
and a view class for the initial view, but this isn't always true -- some
controllers don't have a corresponding model class.

### Doing things in the background

If the UI does not block, as promised above, then there needs to be a way of
running things in the background and subiquity uses
[asyncio](https://docs.python.org/3/library/asyncio.html) for this.
`subiquitycore.async_helpers` defines some useful helpers:

 * `schedule_task` (a wrapper around `create_task` / `ensure_future`)
 * `run_in_thread` (just a nicer wrapper around `run_in_executor`)
    * We still use threads for HTTP requests (this could change in the future
      I guess) and come compute-bound things like generating error reports.
 * `SingleInstanceTask` is a way of running tasks that only need to run once
   but might need to be cancelled and restarted.
   * This is useful for things like checking for snap updates: it's possible
     that network requests will just hang until a HTTP proxy is configured so
     if the request hasn't completed yet when a proxy is configured, we cancel
     and restart.

[trio](https://trio.readthedocs.io/en/stable/) has nicer APIs but is
a bit too new for now.

The older approach which is still present in the codebase is the `run_in_bg`
function, which takes two functions: one that takes no arguments and is called
in a background thread and a callback that takes one argument, and is called
in the main/UI thread with a `concurrent.futures.Future` representing the
result of calling the first function.

A cast-iron rule: Only touch the UI from the main thread.

### Terminal things

Subiquity is mostly developed in a graphical terminal emulator like
gnome-terminal, but ultimately runs for real in a linux tty or over a serial
line.

The main limitation of the linux tty is that it only supports a font with 256
characters (and that's if you use the mode that supports only 8 colors, which
is what subiquity does).  Subiquity comes with its own console font (see the
`font/` subdirectory) that uses different glyphs for arrows and has a check
mark character. gnome-terminal supports utf-8 of course, so that just works
during development -- one just has to be a bit careful when using non-ascii
characters. There are still plenty of characters in the standard font subiquity
does not use, so we can add support for at least a dozen or so more glyphs if
there's a need.

`subiquity.palette` defines the 8 RGB colors and a bunch of named "styles" in
terms of foreground and background colors.  `subiquitycore.core` contains some
rather hair-raising code for mangling these definitions so that using these
style names in urwid comes out in the right color both in gnome-terminal (using
ISO-8613-3 color codes) and in the linux tty (using the PIO_CMAP ioctl).

### Testing

subiquity definitely does not have enough tests.  There are some unit tests for
the views, and a helper module, `subiquitycore.testing.view_helpers`, that
makes writing them a bit easier.

subiquity supports a limited form of automation in the form of an "answers
file". This yaml file provides data that controllers can use to drive the UI
automatically (this is not a replacement for preseeding: that is to be designed
during the 18.10 cycle).  There are some answers files in the `examples/`
directory that are run as a sort of integration test for the UI.

Tests (and lint checks) are run by travis using lxd.  See `.travis.yml` and
`./scripts/test-in-lxd.sh` and so on.

For "real" testing, you need to make a snap (`snapcraft snap`), mash it into an
existing ISO using `./scripts/inject-subiquity-snap.sh`, and boot the result in
a VM.

There are integration tests that run daily at
https://platform-qa-jenkins.ubuntu.com/view/server (unfortunately you need to
be connected to the Canonical VPN -- i.e. be a Canonical staff member -- to
see these results).

## Development process

When adding a new feature to subiquity, I have found it easiest to design the
UI first and then "work inwards" to design the controller and the model.
Subiquity is mostly a UI, after all, so starting there does made sense.  I also
try not to worry about how hard a UI would be to implement!

The model is sometimes quite trivial, because it's basically defined by the
curtin config, and sometimes much less so (e.g. the fileystem model).

Once the view code and the model exist, the controller "just" sits between
them. Again, often this is simple, but sometimes it is not.
