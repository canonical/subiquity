
# vmtests

vmtests for subiquity work by way of virt-install and autoinstall.  SSH is
setup with a passwordless authentication key so that, both at install time and
first boot, the system under test can be automated and analyzed.

See `vmtests/tests/test_basic.py` for a simple example of a vmtest.
See the VMM and VM classes in `vmtests/tests/conftest.py` for more details and
API.

## run

The vmtests expect to run from the subiquity top-level directory. The `--iso`
argument is mandatory.  With python3-xdist and enough memory, the `-n` option
can be used to run multiple tests in parallel - but you probably don't want
`-n auto`.

```
PYTHONPATH=. pytest-3 --iso=$iso vmtests
```
