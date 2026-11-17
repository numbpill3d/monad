# SPDX-License-Identifier: GPL-3.0-or-later
PREFIX ?= /usr
DESTDIR ?=
APP_ID = io.github.numbpill3d.Monad
PYTHON ?= python3

.PHONY: all install test check uninstall

all:
	@echo "Nothing to build. Run 'make install' (XMRig is built separately, see packaging/)."

install:
	install -Dm755 bin/monad $(DESTDIR)$(PREFIX)/bin/monad
	install -d $(DESTDIR)$(PREFIX)/share/monad/monad
	install -m644 monad/*.py $(DESTDIR)$(PREFIX)/share/monad/monad/
	install -Dm644 data/$(APP_ID).desktop $(DESTDIR)$(PREFIX)/share/applications/$(APP_ID).desktop
	install -Dm644 data/$(APP_ID).metainfo.xml $(DESTDIR)$(PREFIX)/share/metainfo/$(APP_ID).metainfo.xml
	install -Dm644 data/icons/hicolor/scalable/apps/$(APP_ID).svg $(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/$(APP_ID).svg
	install -Dm644 data/icons/hicolor/symbolic/apps/$(APP_ID)-symbolic.svg $(DESTDIR)$(PREFIX)/share/icons/hicolor/symbolic/apps/$(APP_ID)-symbolic.svg

test:
	$(PYTHON) -m unittest discover -s tests -v

check: test
	desktop-file-validate data/$(APP_ID).desktop
	appstreamcli validate --no-net data/$(APP_ID).metainfo.xml

uninstall:
	rm -rf $(DESTDIR)$(PREFIX)/bin/monad $(DESTDIR)$(PREFIX)/share/monad \
	  $(DESTDIR)$(PREFIX)/share/applications/$(APP_ID).desktop \
	  $(DESTDIR)$(PREFIX)/share/metainfo/$(APP_ID).metainfo.xml \
	  $(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/$(APP_ID).svg \
	  $(DESTDIR)$(PREFIX)/share/icons/hicolor/symbolic/apps/$(APP_ID)-symbolic.svg
