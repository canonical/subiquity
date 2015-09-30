#
# Makefile for subiquity
#
NAME=subiquity
VERSION=0.0.1
PYTHONSRC=$(NAME)
PYTHONPATH=$(shell pwd):$(shell pwd)/probert
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
PROBERTDIR=./probert
PROBERT_REPO=https://github.com/CanonicalLtd/probert.git
PROBERT_REVNO=e7fa0c6bfb35f00efc68962777db6bb73217231f
GITDEBDIR=./debian.git
DEBDIR=./debian

ifneq (,$(MACHINE))
	MACHARGS=--machine=$(MACHINE)
endif

.PHONY: run clean

all: dryrun

$(NAME)_$(VERSION).orig.tar.gz: probert clean
	cd .. && tar czf $(NAME)_$(VERSION).orig.tar.gz $(shell basename `pwd`) --exclude-vcs --exclude=debian --exclude='.tox*'

tarball: $(NAME)_$(VERSION).orig.tar.gz

install_deps_amd64:
	sudo apt-get install grub-efi-amd64-signed

install_deps: install_deps_$(ARCH)
	sudo apt-get install python3-urwid python3-pyudev python3-netifaces python3-nose python3-flake8 python3-yaml git bzr ubuntu-cloudimage-keyring python3-jinja2 python3-coverage ovmf shim shim-signed

dryrun: probert
	$(MAKE) ui-view DRYRUN="--dry-run --uefi"

ui-view:
	(PYTHONPATH=$(PYTHONPATH) bin/$(PYTHONSRC)-tui $(DRYRUN) $(MACHARGS))

ui-view-serial:
	(TERM=att4424 PYTHONPATH=$(PYTHONPATH) bin/$(PYTHONSRC)-tui $(DRYRUN) --serial)

lint:
	echo "Running flake8 lint tests..."
	flake8 bin/$(PYTHONSRC)-tui --ignore=F403
	flake8 --exclude $(PYTHONSRC)/tests/ $(PYTHONSRC) --ignore=F403

unit:
	echo "Running unit tests..."
	python3 -m "nose" -v --nologcapture --with-coverage ${TOPDIR}/tests/

installer/$(INSTALLIMG): installer/geninstaller installer/runinstaller $(INSTALLER_RESOURCES) probert
	(cd installer && TOPDIR=$(TOPDIR)/installer ./geninstaller -v $(OFFLINE) -r $(RELEASE) -a $(ARCH) -s $(STREAM) -b $(BOOTLOADER)) 
	echo $(INSTALLER_RESOURCES)

installer: installer/$(INSTALLIMG)

run: installer
	(cd installer && INSTALLER=$(INSTALLIMG) ./runinstaller)

probert:
	@if [ ! -d "$(PROBERTDIR)" ]; then \
		git clone -q $(PROBERT_REPO) $(PROBERTDIR); \
		(cd probert && git checkout -f $(PROBERT_REVNO)); \
    fi

git-checkout-deb:
	@if [ ! -d "$(DEBDIR)" ]; then \
		git clone -q https://github.com/CanonicalLtd/subiquity-deb.git $(GITDEBDIR); \
        mv $(GITDEBDIR)/debian $(DEBDIR); \
        rm -fr $(GITDEBDIR); \
    fi

DPKGBUILDARGS = -i'.git.*|.tox|.bzr.*|.editorconfig|.travis-yaml'
deb-src: git-checkout-deb clean tarball
	@dpkg-buildpackage -S -sa $(DPKGBUILDARGS)

deb-release: git-checkout-deb tarball
	@dpkg-buildpackage -S -sd $(DPKGBUILDARGS)

deb: git-checkout-deb
	@dpkg-buildpackage -us -uc -b $(DPKGBUILDARGS)

clean:
	@if [ -d "$(DEBDIR)" ]; then \
        ./debian/rules clean; \
	    rm -rf debian/subiquity; \
	    rm -rf ../$(NAME)_*.deb ../$(NAME)_*.tar.gz ../$(NAME)_$.dsc ../$(NAME)_*.changes \
		    ../$(NAME)_*.build ../$(NAME)_*.upload; \
	    wrap-and-sort; \
    fi
	rm -f installer/target.img
	rm -f installer/installer.img
	rm -f installer/geninstaller.log
	find installer -type f -name *-installer.img | xargs -i rm {}
