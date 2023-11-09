
Thank you for considering a contribution to Subiquity.  Here are some things to
note:

## Code of Conduct

This project is subject to the [Ubuntu Code of Conduct](https://ubuntu.com/community/code-of-conduct)
to foster an open and welcoming place to contribute. By participating in the
project (in the form of code contributions, issues, comments, and other
activities), you agree to abide by its terms.

## Contributor License Agreement

This project is subject to the
[Canonical contributor license agreement](https://ubuntu.com/legal/contributors),
please make sure you have [signed it](https://ubuntu.com/legal/contributors/agreement)
before (or shortly after) submitting your first pull request.

A github workflow will verify that your GitHub username or email address is
associated with a contributor license agreement signature, but it may take
some time after your initial signature for the check to see it. If you're
part of [@canonical](https://github.com/canonical), you will also need to make
sure your canonical.com email address is associated with your GitHub account.

## Bugs
Bugs are tracked on [Launchpad](https://bugs.launchpad.net/subiquity). It is
recommended you use `ubuntu-bug` (or similar) to let apport collect relevant
logs which are helpful for the debug process, instead of filing one directly.

## Pull Requests
Changes to this project should be proposed as pull requests on GitHub at:
[https://github.com/canonical/subiquity/](https://github.com/canonical/subiquity/)


 Format, lint, unit, integration, and API tests should be passing.
  * format - run either `make format` or `pre-commit install`.
    * Install pre-commit with `sudo apt install pre-commit`.
  * all the rest - `make lint check`.
    * Prerequisites for running these locally can be installed with
    `make aptdeps`.
