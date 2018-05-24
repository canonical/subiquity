#
# Makefile for subiquity
#
NAME=subiquity
PYTHONSRC=$(NAME)
PYTHONPATH=$(shell pwd):$(shell pwd)/probert
PROBERTDIR=./probert
PROBERT_REPO=https://github.com/CanonicalLtd/probert
export PYTHONPATH
CWD := $(shell pwd)

ifneq (,$(MACHINE))
	MACHARGS=--machine=$(MACHINE)
endif

.PHONY: run clean check

all: dryrun

install_deps:
	sudo apt-get install -y python3-urwid python3-pyudev python3-nose python3-flake8 \
		python3-yaml python3-coverage python3-dev pkg-config libnl-genl-3-dev \
		libnl-route-3-dev python3-attr python3-distutils-extra python3-requests \
		python3-requests-unixsocket

i18n:
	python3 setup.py build

dryrun: probert i18n
	$(MAKE) ui-view DRYRUN="--dry-run --uefi"

ui-view:
	(bin/$(PYTHONSRC)-tui $(DRYRUN) $(MACHARGS))

ui-view-serial:
	(TERM=att4424 bin/$(PYTHONSRC)-tui $(DRYRUN) --serial)

lint: pep8 pyflakes3

pep8:
	@$(CWD)/scripts/run-pep8

pyflakes3:
	@$(CWD)/scripts/run-pyflakes3

unit:
	echo "Running unit tests..."
	nosetests3 $(PYTHONSRC)/tests

check: lint unit

probert:
	@if [ ! -d "$(PROBERTDIR)" ]; then \
		git clone -q $(PROBERT_REPO) $(PROBERTDIR); \
		(cd probert && python3 setup.py build_ext -i); \
    fi

clean:
	./debian/rules clean

.PHONY: lint pyflakes3 pep8
