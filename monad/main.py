# SPDX-License-Identifier: GPL-3.0-or-later
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk  # noqa: E402

from . import constants as C  # noqa: E402
from .window import MonadWindow  # noqa: E402


class MonadApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=C.APP_ID,
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.win = None
        for name, cb, accels in (
            ("about", self.on_about, None),
            ("fee", lambda *_: self.win and self.win.show_fee_dialog(), None),
            ("quit", lambda *_: self.quit(), ["<primary>q"]),
        ):
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", cb)
            self.add_action(act)
            if accels:
                self.set_accels_for_action(f"app.{name}", accels)
        self.set_accels_for_action("window.close", ["<primary>w"])

    def do_activate(self):
        if not self.win:
            self.win = MonadWindow(self)
        self.win.present()

    def do_shutdown(self):
        if self.win and self.win.miner.running:
            self.win.miner.stop()
        Adw.Application.do_shutdown(self)

    def on_about(self, *_):
        about = Adw.AboutDialog(
            application_name=C.APP_NAME,
            application_icon=C.APP_ID,
            developer_name="numbpill3d",
            version=C.VERSION,
            website=C.WEBSITE,
            issue_url=C.ISSUES,
            license_type=Gtk.License.GPL_3_0,
            comments="A minimalist Monero miner.\n\n2% of hashing time is mined to "
                     "the developer to fund the project.",
        )
        about.add_credit_section("Mining engine", ["XMRig https://xmrig.com"])
        about.present(self.win)


def main():
    return MonadApp().run(sys.argv)
