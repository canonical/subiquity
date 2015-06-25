#
# Makefile for subiquity
#
PYTHONSRC=subiquity
STREAM=daily
RELEASE=wily
ARCH=amd64
INSTALLIMG=ubuntu-server-${STREAM}-${RELEASE}-${ARCH}-installer.img
INSTALLER_RESOURCES += $(shell find installer/resources -type f)
.PHONY: run clean


ui-view:
	(PYTHONPATH=$(shell pwd) bin/$(PYTHONSRC))

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
