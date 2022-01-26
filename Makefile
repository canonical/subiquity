#
# Makefile for subiquity
#
NAME=subiquity
PYTHONSRC=$(NAME)
PYTHONPATH=$(shell pwd):$(shell pwd)/probert:$(shell pwd)/curtin
PROBERTDIR=./probert
PROBERT_REPO=https://github.com/canonical/probert
DRYRUN?=--dry-run --bootloader uefi --machine-config examples/simple.json \
	--source-catalog examples/install-sources.yaml
SYSTEM_SETUP_DRYRUN?=--dry-run
export PYTHONPATH
CWD := $(shell pwd)

CHECK_DIRS := console_conf/ subiquity/ subiquitycore/ system_setup/
PYTHON := python3

ifneq (,$(MACHINE))
	MACHARGS=--machine=$(MACHINE)
endif

.PHONY: all
all: dryrun

.PHONY: aptdeps
aptdeps:
	sudo apt update && \
	sudo apt-get install -y python3-urwid python3-pyudev python3-nose python3-flake8 \
		python3-yaml python3-coverage python3-dev pkg-config libnl-genl-3-dev \
		libnl-route-3-dev python3-attr python3-distutils-extra python3-requests \
		python3-requests-unixsocket python3-jsonschema python3-apport \
		python3-bson xorriso isolinux python3-aiohttp cloud-init ssh-import-id \
		curl jq build-essential python3-pytest python3-async-timeout \
	        language-selector-common fuseiso python3-pytest-xdist

.PHONY: install_deps
install_deps: aptdeps gitdeps

.PHONY: i18n
i18n:
	$(PYTHON) setup.py build_i18n
	cd po; intltool-update -r -g subiquity

.PHONY: dryrun ui-view
dryrun ui-view: probert i18n
	$(PYTHON) -m subiquity $(DRYRUN) $(MACHARGS)

.PHONY: dryrun-console-conf ui-view-console-conf
dryrun-console-conf ui-view-console-conf:
	$(PYTHON) -m console_conf.cmd.tui --dry-run $(MACHARGS)

.PHONY: dryrun-serial ui-view-serial
dryrun-serial ui-view-serial:
	(TERM=att4424 $(PYTHON) -m subiquity $(DRYRUN) --serial)

.PHONY: dryrun-server
dryrun-server:
	$(PYTHON) -m subiquity.cmd.server $(DRYRUN)

.PHONY: dryrun-system-setup
dryrun-system-setup:
	$(PYTHON) -m system_setup.cmd.tui $(SYSTEM_SETUP_DRYRUN)

.PHONY: dryrun-system-setup-server
dryrun-system-setup-server:
	$(PYTHON) -m system_setup.cmd.server $(SYSTEM_SETUP_DRYRUN)

.PHONY: dryrun-system-setup-recon
dryrun-system-setup-recon:
	DRYRUN_RECONFIG=true $(PYTHON) -m system_setup.cmd.tui $(SYSTEM_SETUP_DRYRUN)

.PHONY: dryrun-system-setup-server-recon
dryrun-system-setup-server-recon:
	DRYRUN_RECONFIG=true $(PYTHON) -m system_setup.cmd.server $(SYSTEM_SETUP_DRYRUN)

.PHONY: lint
lint: flake8

.PHONY: flake8
flake8:
	@echo 'tox -e flake8' is preferred to 'make flake8'
	$(PYTHON) -m flake8 $(CHECK_DIRS)

.PHONY: unit
unit: gitdeps
	$(PYTHON) -m pytest --ignore curtin --ignore probert \
		--ignore subiquity/tests/api

.PHONY: api
api: gitdeps
	$(PYTHON) -m pytest -n auto subiquity/tests/api

.PHONY: integration
integration: gitdeps
	echo "Running integration tests..."
	./scripts/runtests.sh

.PHONY: check
check: unit integration api

curtin: snapcraft.yaml
	./scripts/update-part.py curtin

probert: snapcraft.yaml
	./scripts/update-part.py probert
	(cd probert && $(PYTHON) setup.py build_ext -i);

.PHONY: gitdeps
gitdeps: curtin probert

.PHONY: schema
schema: gitdeps
	@$(PYTHON) -m subiquity.cmd.schema > autoinstall-schema.json
	@$(PYTHON) -m system_setup.cmd.schema > autoinstall-system-setup-schema.json

.PHONY: clean
clean:
	./debian/rules clean
