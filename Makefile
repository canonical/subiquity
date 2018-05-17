#
# Makefile for subiquity
#
NAME=subiquity
PYTHONSRC=$(NAME)
PYTHONPATH=$(shell pwd):$(shell pwd)/probert
PROBERTDIR=./probert
PROBERT_REPO=https://github.com/CanonicalLtd/probert

ifneq (,$(MACHINE))
	MACHARGS=--machine=$(MACHINE)
endif

.PHONY: run clean check

all: dryrun

install_deps:
	sudo apt-get install -y python3-urwid python3-pyudev python3-nose python3-flake8 \
		python3-yaml python3-coverage python3-dev pkg-config libnl-genl-3-dev \
		libnl-route-3-dev python3-attr python3-distutils-extra


i18n:
	python3 setup.py build

dryrun: probert i18n
	$(MAKE) ui-view DRYRUN="--dry-run --uefi"

ui-view:
	(PYTHONPATH=$(PYTHONPATH) bin/$(PYTHONSRC)-tui $(DRYRUN) $(MACHARGS))

ui-view-serial:
	(TERM=att4424 PYTHONPATH=$(PYTHONPATH) bin/$(PYTHONSRC)-tui $(DRYRUN) --serial)

lint:
	echo "Running flake8 lint tests..."
	python3 /usr/bin/flake8 bin/$(PYTHONSRC)-tui --ignore=F403
	python3 /usr/bin/flake8 --exclude $(PYTHONSRC)/tests/ $(PYTHONSRC) --ignore=F403

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
