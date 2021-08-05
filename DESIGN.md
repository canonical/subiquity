# subiquity design notes

## UI

### basic ground rules:

1. Subiquity is entirely usable by pressing up, down, space (or return) and the
   occasional bit of typing.

2. The UI never blocks.  If something takes more than about 0.1s, it is done in
   the background, possibly with some kind of indication in the UI and the
   ability to cancel if appropriate.  If indication is shown, it is shown for
   at least 1s to avoid flickering the UI.  There is a helper,
   `wait_with_text_dialog` for this.

3. General UX principles that it is worth keeping in mind:

    1. Prevent invalid use if that makes sense (e.g. unix usernames can never
       contain spaces, so you simply can't enter spaces in that box)

    2. When rejecting input, be clear about that to the user and explain what
       they need to do differently (e.g. when you do try to put a space in a
       unix username, a message appears explaining which characters are valid).

    3. Make the common case as easy as possible by doing things like thinking
       about which widget should be highlighted when a screen is first shown.

4. Subiquity is functional in an 80x24 terminal.  It doesn't matter if it
   becomes unusable in a smaller terminal (although it shouldn't crash, as we
   support people logging in via ssh and they can resize their terminal
   however they like) and obviously you can get more information on a larger
   terminal at once, but it needs to work in 80x24.

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

### Overall architecture

Subiquity has a client / server model: there is one server, which collects the
data that will go into the curtin config and runs the install, and one or more
client processes which connect to it.  One client runs on tty1 (apart from on
s390x) and others run on any configured serial console.  One can also ssh into
the live session as another way of starting a client.

Subiquity follows a model / view / controller sort of approach, where the model
lives in the server and the view in the client, and controller classes in both
the server and client handle the communication.

The model is ultimately the config that will be passed to curtin, which is
broken apart into classes for the configuration of the network, the filesystem,
the language, etc, etc.  The full model lives in `subiquity.models.subiquity`
and the submodels live in modules like `subiquitycore.models.network` and
`subiquity.models.keyboard`. Each model object gets an `asyncio.Event` object
associated with it that is set when the model is ready to be used as part of
the installation.

Subiquity presents itself as a series of screens -- Welcome, Keyboard, Network,
etc etc -- as described above.  Each screen is managed by an instance of a
controller class. The controller also manages the relationship between the
outside world and the model and views -- in the network view, it is the
controller that listens to netlink events and calls methods on the model and
view instances in response to, say, a NIC gaining an address.

Obviously for most screens there is a tuple (model class, server controller
class, client controller class, view class), but this isn't always true -- some
screens like the one offering the installer refresh don't have a corresponding
model class.

### API details

The api is HTTP over a unix socket (/run/subiquity/socket). It is defined in
the `subiquity.common.apidef` module, and is all fairly ad hoc and designed as
needed.  The API uses basic Python types, classes defined by
[attrs](https://attrs.org) and enums and there is general machinery for
converting these to and from JSON, building a client from the api definition
and serving bits of the API from a particular class.

The API takes a "long poll" approach to status updates. For example,
`refresh.GET()` takes a wait boolean. The refresh view calls this with
`wait=False` and if the result indicates that the check for updates is still in
progress it shows a screen indicating this and calls it again with `wait=True`,
which will not return until the check has completed (or failed). In a similar
vein, `meta.status.GET()` takes an argument indicating what the client
thinks the application state currently is and will block until that changes.

### Examples and common patterns

Adding a typical screen requires:

 1. Implementing the model class.
 2. Defining the API
 3. Implementing the server controller
 4. Implementing the client controller
 5. Implementing the view

(Although it often makes most sense to work in the opposite order when
designing a new feature).

#### Implementing the model class

There is no generic way to describe the data being modelled of course.  Model
classes live in `subiquity.models`.  An instance of each model class is
attached as an attribute to the `SubiquityModel` class and the name of the
attribute added to `INSTALL_MODEL_NAMES` or `POSTINSTALL_MODEL_NAMES` as
appropriate. Models that go into `INSTALL_MODEL_NAMES` need to define a
render() method that returns a fragment of curtin config.  POSTINSTALL models
that contribute to cloud-config should define a make_cloudconfig() method that
returns a cloud config fragment.

#### Defining the API

The simplest API is one where the values are retrieved with a GET request when
the screen is shown and set with a POST when the screen is finished. This can
be done by adding a line like:

```
    example = simple_endpoint(Type)
```

to `subiquity.common.apidef`.

#### Implementing the server controller

The simplest possible server controller would be something like this:

```
import logging

from subiquity.common.apidef import API
from subiquity.common.types import Type
from subiquity.server.controller import SubiquityController

log = logging.getLogger('subiquity.server.controllers.example')


class ExampleController(SubiquityController):

    endpoint = API.example
    model_name = 'example'

    async def GET(self) -> Type:
        return self.model.thing

    async def POST(self, data: Type):
        self.model.thing = data
        self.configured()
```

Setting `endpoint` is how the API methods are routed to this class.

There are other attributes to set and methods to implement to handle
autoinstalls and starting asynchronous tasks when the installer starts up.

The `GET` method can raise `Skip` to indicate that this screen should not be
shown to the user.

The name of the controller needs to be added to the list in
`subiquity.server.server`.

The `configured` method needs to be called when the associated model object is
ready to be used by other parts of the installer.

#### Implementing the client controller

The simplest possible client controller would be something like this:

```
import logging

from subiquity.client.controller import SubiquityTuiController
from subiquity.ui.views.example import ExampleView

log = logging.getLogger('subiquity.client.controllers.example')


class ExampleController(SubiquityTuiController):

    endpoint_name = 'example'

    async def make_ui(self):
        thing = await self.endpoint.GET()
        return ExampleView(self, thing)

    def cancel(self):
        self.app.prev_screen()

    def done(self, thing):
        self.app.next_screen(self.endpoint.POST(thing))
```

Setting `endpoint_name` means that self.client gets set to an implementation of
that part of the API.

The name of the controller needs to be added to the list in
`subiquity.client.client`.

#### Implementing the view

A simple view might look like this:

```
import logging
from urwid import connect_signal

from subiquitycore.view import BaseView
from subiquitycore.ui.form import (
    Form,
    ThingField,
)


log = logging.getLogger('subiquity.ui.views.example')


class ExampleForm(Form):

    thing = ThingField(_("Thing:"))


class ExampleView(BaseView):

    title = _("Configure example")

    def __init__(self, controller, thing):
        self.controller = controller

        self.form = ThingForm(initial={'thing': thing})

        connect_signal(self.form, 'submit', self.done)
        connect_signal(self.form, 'cancel', self.cancel)

        super().__init__(self.form.as_screen())

    def done(self, result):
        self.controller.done(result.thing.value)

    def cancel(self, result=None):
        self.controller.cancel()
```

### autoinstalls

As documented at https://ubuntu.com/server/docs/install/autoinstall,
autoinstalls are subiquity's way of doing a automated, or partially automated
install. This mostly impacts the server, which loads the config and the server
controllers have methods that are called to load and apply the autoinstall data
for each controller. The only real difference to the client is that it behaves
totally differently if the install is to be totally automated: in this case it
does not start the urwid-based UI at all and mostly just "listens" to install
progress via journald and the `meta.status.GET()` API call.

### The server state machine

The server code proceeds in stages:

 1. It starts up, checks for an autoinstall config and runs any early
    commands.
 2. Then it waits for all the model objects that feed into the curtin
    config to be configured.
 3. It waits for confirmation. This can in theory be interrupted by a
    change in the model objects which are considered 'interesting',
    see below, so it is possible to transition from here to the
    previous state.
 4. It runs "curtin install" and waits for that to finish.
 5. It waits for the model objects that feed into the cloud-init config to be
    configured.
 6. It creates the cloud-init config for the first boot of the
    installed system.
 7. If there appears to be a working network connection, it downloads and
    installs security updates.
 8. It runs any late commands.
 9. It waits for the user to click "reboot".

Each of these states gets a different value of the `ApplicationState`
enum, so the client gets notified via long-polling `meta.status.GET()`
of progress. In addition, `ApplicationState.ERROR` indicates something
has gone wrong.

Originally subiquity was just the server installer and so the set of
models that have to be configured for each step was just static. But
subiquity can also install desktop systems and maybe one day Ubuntu
core, and different information is needed to fully configure each
different variant. This information is handled by the
`subiquity.models.subiquity.SubiquityModel.set_source_variant` method
and surrounding code.

### Error handling

As hard as it is to believe, things do go wrong during
installation. It was helpful to me when working on this to categorize
4 kinds of error:

 * **immediate** errors need to be shown to the user immediately and
   mean no further progress can be made.
   * The installation failing is the canonical example of this.
   * Other immediate errors include:
     * A bug leading to an unhandled exception in the server process.
     * The autoinstall.yaml file not being valid yaml.
     * The autoinstall config failing schema validation.
     * An early-command failing.
     * A late-command failing.
   * An immediate error results in the error-commands from the
     autoinstall config, if any, being run.
 * **delayed** errors are not shown to the user until they become critical.
   * The only example of this at the time of writing is block probe
     errors. These are not reported until the filesystem screen, at
     least in part because a snap update may resolve them, so the user
     needs to be able to get to that screen before being bothered about them.
   * When the filesystem screen is not interactive, these errors
     errors are handled as if an immediate error occured when the
     filesystem config is needed.
 * **API** errors are when an exception occurs while handling an API
   call from the client.
   * These are always bugs and perhaps could be handled as immediate
     errors but it is easy to let the user try something else in this
     context so we do that.
   * For a non-interactive install, the client does not make API calls
     (well apart from the status-tracking one: if that fails, the
     client treats it as an internal error) so no special handling is
     required.
 * **client** errors are when a bug in the client leads to an
   unhandled error.

All of these errors result in an error report (using the same format
as apport) being generated, before the error-commands (if any) are
run.

Error reports are represented over the API by the `ErrorReportRef`
type. This contains enough information to find the error report and
know if it is complete yet (there is an API method `errors.wait.GET()`
that will block until the error report has been completed).

Immediate errors end up in the `error` field in the return value for
`meta.status.GET()`.

When an API error happens, the server puts a serialized
`ErrorReportRef` in the `x-error-report` header of the response.

Some things that could be considered "errors", like failing to contact
the snap store are ignored and not presented to the user, instead the
relevant screens are skipped.

### Refreshing the snap

The installer checks for a snap update and offers it to the user if one is
available. If the users says yes, the new version is downloaded and the
installer, both server and client restarts where it left off. This restarting
is all a bit more complicated that it perhaps needs to be.

For the server process and the client running on tty1, the actual restarting of
the processes is trivial: systemd does it as part of the snap refresh. There is
also a snap hook that restarts any clients running on serial lines. But any
clients running over SSH have to notice the snap update has completed and
restart themselves.

In dry-run mode, there is some more hair:

 * the server notices when the canned snapd progress updates indicate the
   refresh has completed and restarts itself to simulate systemd doing it.

 * as the client autostarts a server process if needed and there is some
   complication around making sure that the server is killed when the client
   exits, even after a restart.

But this is all hidden away behind "if dry_run:" checks so I don't feel too bad
about it being a bit fragile.

The "Restarting where it left off" is also a bit complicated.

The server records any needed state in /run/subiquity/$controller_name to be
read on restart (the keyboard controller does not need to do this, for example,
because the keyboard settings can be reconstructed from
/etc/default/keyboard. The proxy controller does need to do this though).

The client records which screen it is on in /run/subiquity/last-screen and when
it restarts it checks this file and skips to this screen (it also asks the
server to mark all controllers before this screen as configured).

### Doing things in the background

If the UI does not block, as promised above, then there needs to be a way of
running things in the background and subiquity uses
[asyncio](https://docs.python.org/3/library/asyncio.html) for this.
`subiquitycore.async_helpers` defines some useful helpers:

 * `schedule_task` (a wrapper around `create_task` / `ensure_future`)
 * `run_in_thread` (just a nicer wrapper around `run_in_executor`)
    * We still use threads for HTTP requests (this could change in the future
      I guess) and some compute-bound things like generating error reports.
 * `SingleInstanceTask` is a way of running tasks that only need to run once
   but might need to be cancelled and restarted.
   * This is useful for things like checking for snap updates: it's possible
     that network requests will just hang until a HTTP proxy is configured so
     if the request hasn't completed yet when a proxy is configured, we cancel
     and restart.

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
terms of foreground and background colors.  `subiquitycore.screen` contains some
rather hair-raising code for mangling these definitions so that using these
style names in urwid comes out in the right color both in gnome-terminal (using
ISO-8613-3 color codes) and in the linux tty (using the PIO_CMAP ioctl).

### Testing

subiquity definitely does not have enough tests.  There are some unit tests for
the views, and a helper module, `subiquitycore.testing.view_helpers`, that
makes writing them a bit easier.

subiquity supports a limited form of automation in the form of an "answers
file". This yaml file provides data that controllers can use to drive the UI
automatically.  There are some answers files in the `examples/` directory that
are run as a sort of integration test for the UI.

Tests (and lint checks) are run by github actions using lxd.  See
`.github/workflows/build.yaml` and `./scripts/test-in-lxd.sh` and so
on.

For "real" testing, you need to make a snap (`snapcraft snap`), mash
it into an existing ISO using `./scripts/inject-subiquity-snap.sh`,
and boot the result in a VM. There is an even hackier pair of scripts
(`./scripts/slimy-update-snap.sh` and
`./scripts/quick-test-this-branch.sh`) that can be useful for getting
small changes into an ISO much more quickly than making the snap from
scratch.

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
