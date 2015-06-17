#
# Makefile for subiquity
#
STREAM=daily
RELEASE=wily
ARCH=amd64
INSTALLIMG=ubuntu-server-${STREAM}-${RELEASE}-${ARCH}-installer.img
INSTALLER_RESOURCES += $(shell find installer/resources -type f)
.PHONY: run clean


ui-view:
	(PYTHONPATH=$(shell pwd) bin/subiquity)

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
