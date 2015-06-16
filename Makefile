#
# Makefile for subiquity
#
STREAM=daily
RELEASE=wily
ARCH=amd64
INSTALLIMG=ubuntu-server-${STREAM}-${RELEASE}-${ARCH}-installer.img
.PHONY: installer run clean

ui-view:
	(PYTHONPATH=$(shell pwd) bin/subiquity)

installer:
	[ -e "installer/$(INSTALLIMG)" ] || \
	(cd installer && ./geninstaller -v -r $(RELEASE) -a $(ARCH) -s $(STREAM))

run: installer
	(cd installer && INSTALLER=$(INSTALLIMG) ./runinstaller)

clean:
	rm -f installer/target.img
	rm -f installer/installer.img
	rm -f installer/geninstaller.log
	find installer -type f -name *-installer.img | xargs -i rm {}

