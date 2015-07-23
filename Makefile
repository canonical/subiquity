#
# Makefile for subiquity
#
PYTHONSRC=subiquity
PYTHONPATH=$(shell pwd):$(HOME)/download/probert:
VENVPATH=$(shell pwd)/venv
VENVACTIVATE=$(VENVPATH)/bin/activate
TOPDIR=$(shell pwd)
STREAM=daily
RELEASE=wily
ARCH=amd64
INSTALLIMG=ubuntu-server-${STREAM}-${RELEASE}-${ARCH}-installer.img
INSTALLER_RESOURCES += $(shell find installer/resources -type f)
.PHONY: run clean

all: dryrun

install_deps:
	sudo apt-get install python3-urwid python3-pyudev python3-netifaces python3-nose python3-flake8 python3-parted python3-yaml git bzr ubuntu-cloudimage-keyring python3-jinja2

dryrun:
	$(MAKE) ui-view DRYRUN="--dry-run"

ui-view:
	(PYTHONPATH=$(PYTHONPATH) bin/$(PYTHONSRC) $(DRYRUN))

ui-view-serial:
	(TERM=att4424 PYTHONPATH=$(PYTHONPATH) bin/$(PYTHONSRC) $(DRYRUN) --serial)

lint:
	echo "Running flake8 lint tests..."
	flake8 bin/$(PYTHONSRC) --ignore=F403
	flake8 --exclude $(PYTHONSRC)/tests/ $(PYTHONSRC) --ignore=F403

unit:
	echo "Running unit tests..."
	python3 -m "nose" -v --nologcapture --with-coverage $(PYTHONSRC)/tests/

installer/$(INSTALLIMG): installer/geninstaller installer/runinstaller $(INSTALLER_RESOURCES)
	(cd installer && ./geninstaller -v -r $(RELEASE) -a $(ARCH) -s $(STREAM))
	echo $(INSTALLER_RESOURCES)

installer: installer/$(INSTALLIMG)

run: installer
	(cd installer && INSTALLER=$(INSTALLIMG) ./runinstaller)

clean:
	rm -f installer/target.img
	rm -f installer/installer.img
	rm -f installer/geninstaller.log
	find installer -type f -name *-installer.img | xargs -i rm {}
