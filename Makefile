#
# Makefile for subiquity
#
NAME=subiquity
PYTHONSRC=$(NAME)
PYTHONPATH=$(shell pwd):$(shell pwd)/probert:$(shell pwd)/curtin
PROBERTDIR=./probert
PROBERT_REPO=https://github.com/canonical/probert
DRYRUN?=--dry-run --bootloader uefi --machine-config examples/machines/simple.json \
	--source-catalog examples/sources/install.yaml \
	--postinst-hooks-dir examples/postinst.d/
UNITTESTARGS?=
COVERAGEARGS:=--cov=subiquity --cov=subiquitycore --cov=console_conf
COVERAGEARGS+=--cov-report xml:.coverage/cobertura.xml
export PYTHONPATH
CWD := $(shell pwd)

CHECK_DIRS := console_conf subiquity subiquitycore
PYTHON := python3

ifneq (,$(MACHINE))
	MACHARGS=--machine=$(MACHINE)
endif

.PHONY: all
all: dryrun

.PHONY: aptdeps
aptdeps:
	sudo apt update && \
	sudo apt-get install -y $(shell cat apt-deps.txt)

.PHONY: install_deps
install_deps: aptdeps gitdeps

.PHONY: i18n
i18n:
	$(PYTHON) setup.py build_i18n
	cd po; intltool-update -r -g subiquity

.PHONY: dryrun ui-view
dryrun ui-view: probert i18n
	$(PYTHON) -m subiquity $(DRYRUN) $(MACHARGS)

.PHONY: dryrun-debug-sv2
dryrun-debug-sv2: probert i18n
	$(PYTHON) -m subiquity $(DRYRUN) $(MACHARGS) --storage-version=2 --debug-sv2-guided

.PHONY: dryrun-console-conf ui-view-console-conf
dryrun-console-conf ui-view-console-conf:
	$(PYTHON) -m console_conf.cmd.tui --dry-run $(MACHARGS)

.PHONY: dryrun-serial ui-view-serial
dryrun-serial ui-view-serial:
	(TERM=att4424 $(PYTHON) -m subiquity $(DRYRUN) --serial)

.PHONY: dryrun-server
dryrun-server:
	$(PYTHON) -m subiquity.cmd.server $(DRYRUN)

.PHONY: lint
lint: flake8

.PHONY: flake8
flake8:
	$(PYTHON) -m flake8 $(CHECK_DIRS)

.PHONY: unit
unit: gitdeps
	timeout 120 \
	$(PYTHON) -m pytest --ignore curtin --ignore probert \
		--ignore subiquity/tests/api \
		$(UNITTESTARGS)

coverage:
	$(MAKE) unit UNITTESTARGS="$(COVERAGEARGS)"

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
	(cd probert && $(PYTHON) setup.py build_ext --inplace);

.PHONY: gitdeps
gitdeps: curtin probert

.PHONY: schema
schema: gitdeps
	@$(PYTHON) -m subiquity.cmd.schema > autoinstall-schema.json

.PHONY: format black isort
format: black isort
black isort:
	pre-commit run -a $@

.PHONY: clean
clean:
	./debian/rules clean
