#
# Makefile for subiquity
#
NAME=subiquity
VERSION=0.0.1
PYTHONSRC=$(NAME)
PYTHONPATH=$(shell pwd):$(HOME)/download/probert:
VENVPATH=$(shell pwd)/venv
VENVACTIVATE=$(VENVPATH)/bin/activate
TOPDIR=$(shell pwd)
STREAM=daily
RELEASE=wily
ARCH=amd64
BOOTLOADER=grub2
OFFLINE=-o
INSTALLIMG=ubuntu-server-${STREAM}-${RELEASE}-${ARCH}-installer.img
INSTALLER_RESOURCES += $(shell find installer/resources -type f)
GITDEBDIR=/tmp/subiquity-deb
DEBDIR=./debian
.PHONY: run clean

all: dryrun

$(NAME)_$(VERSION).orig.tar.gz: clean
	cd .. && tar czf $(NAME)_$(VERSION).orig.tar.gz $(shell basename `pwd`) --exclude-vcs --exclude=debian --exclude='.tox*'

tarball: $(NAME)_$(VERSION).orig.tar.gz

install_deps:
	sudo apt-get install python3-urwid python3-pyudev python3-netifaces python3-nose python3-flake8 python3-parted python3-yaml git bzr ubuntu-cloudimage-keyring python3-jinja2 python3-coverage

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
	python3 -m "nose" -v --nologcapture --with-coverage ${TOPDIR}/tests/

installer/$(INSTALLIMG): installer/geninstaller installer/runinstaller $(INSTALLER_RESOURCES)
	(cd installer && ./geninstaller -v $(OFFLINE) -r $(RELEASE) -a $(ARCH) -s $(STREAM) -b $(BOOTLOADER)) 
	echo $(INSTALLER_RESOURCES)

installer: installer/$(INSTALLIMG)

run: installer
	(cd installer && INSTALLER=$(INSTALLIMG) ./runinstaller)

git-checkout-deb:
	@if [ ! -d "$(GITDEBDIR)" ]; then \
		git clone -q https://github.com/CanonicalLtd/subiquity-deb.git $(GITDEBDIR); \
	fi
	@if [ ! -h "$(DEBDIR)" ]; then \
		ln -sf $(GITDEBDIR)/debian $(DEBDIR); \
	fi
DPKGBUILDARGS = -us -uc -i'.git.*|.tox|.bzr.*|.editorconfig|.travis-yaml'
deb-src: git-checkout-deb clean tarball
	@dpkg-buildpackage -S -sa $(DPKGBUILDARGS)

deb-release: git-checkout-deb
	@dpkg-buildpackage -S -sd $(DPKGBUILDARGS)

deb: git-checkout-deb
	@dpkg-buildpackage -b $(DPKGBUILDARGS)

clean:
	@-debian/rules clean
	@rm -rf debian/subiquity
	@rm -rf ../$(NAME)_*.deb ../$(NAME)_*.tar.gz ../$(NAME)_$.dsc ../$(NAME)_*.changes \
		../$(NAME)_*.build ../$(NAME)_*.upload
	wrap-and-sort
	rm -f installer/target.img
	rm -f installer/installer.img
	rm -f installer/geninstaller.log
	find installer -type f -name *-installer.img | xargs -i rm {}
