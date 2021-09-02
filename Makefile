#
# Makefile for subiquity
#
NAME=subiquity
PYTHONSRC=$(NAME)
PYTHONPATH=$(shell pwd):$(shell pwd)/probert:$(shell pwd)/curtin
PROBERTDIR=./probert
PROBERT_REPO=https://github.com/canonical/probert
DRYRUN?=--dry-run --bootloader uefi --machine-config examples/simple.json
SYSTEM_SETUP_DRYRUN?=--dry-run
export PYTHONPATH
CWD := $(shell pwd)

CHECK_DIRS := console_conf/ subiquity/ subiquitycore/ system_setup/
PYTHON := python3

ifneq (,$(MACHINE))
	MACHARGS=--machine=$(MACHINE)
endif

.PHONY: run clean check

all: dryrun

aptdeps:
	sudo apt update && \
	sudo apt-get install -y python3-urwid python3-pyudev python3-nose python3-flake8 \
		python3-yaml python3-coverage python3-dev pkg-config libnl-genl-3-dev \
		libnl-route-3-dev python3-attr python3-distutils-extra python3-requests \
		python3-requests-unixsocket python3-jsonschema python3-apport \
		python3-bson xorriso isolinux python3-aiohttp cloud-init ssh-import-id \
		curl jq build-essential

install_deps: aptdeps gitdeps

i18n:
	$(PYTHON) setup.py build_i18n
	cd po; intltool-update -r -g subiquity

dryrun ui-view: probert i18n
	$(PYTHON) -m subiquity $(DRYRUN) $(MACHARGS)

dryrun-console-conf ui-view-console-conf:
	$(PYTHON) -m console_conf.cmd.tui --dry-run $(MACHARGS)

dryrun-serial ui-view-serial:
	(TERM=att4424 $(PYTHON) -m subiquity $(DRYRUN) --serial)

dryrun-server:
	$(PYTHON) -m subiquity.cmd.server $(DRYRUN)

dryrun-system-setup:
	$(PYTHON) -m system_setup.cmd.tui $(SYSTEM_SETUP_DRYRUN)

dryrun-system-setup-server:
	$(PYTHON) -m system_setup.cmd.server $(SYSTEM_SETUP_DRYRUN)

dryrun-system-setup-recon:
	DRYRUN_RECONFIG=true $(PYTHON) -m system_setup.cmd.tui $(SYSTEM_SETUP_DRYRUN)

dryrun-system-setup-server-recon:
	DRYRUN_RECONFIG=true $(PYTHON) -m system_setup.cmd.server $(SYSTEM_SETUP_DRYRUN)

lint: flake8

flake8:
	@echo 'tox -e flake8' is preferred to 'make flake8'
	$(PYTHON) -m flake8 $(CHECK_DIRS) --exclude gettext38.py,contextlib38.py

unit: gitdeps
	python3 -m unittest discover

integration: gitdeps
	echo "Running integration tests..."
	./scripts/runtests.sh

check: unit integration

curtin: snapcraft.yaml
	./scripts/update-part.py curtin

probert: snapcraft.yaml
	./scripts/update-part.py probert
	(cd probert && $(PYTHON) setup.py build_ext -i);

gitdeps: curtin probert

schema: gitdeps
	@$(PYTHON) -m subiquity.cmd.schema > autoinstall-schema.json

clean:
	./debian/rules clean

.PHONY: flake8 lint
