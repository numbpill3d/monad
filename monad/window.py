# SPDX-License-Identifier: GPL-3.0-or-later
import json
import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from . import constants as C  # noqa: E402
from . import fee  # noqa: E402
from .address import is_valid_address  # noqa: E402
from .miner import Miner  # noqa: E402

FEE_TEXT = (
    "Monad is free software. To fund development, 2% of your hashing time "
    "(about 1 minute in every 50) is spent mining to the developer's wallet "
    "on pool.supportxmr.com. The rest goes to your wallet on the pool you "
    "choose.\n\nWhile the fee runs, the status line says “Developer fee”. "
    "Time is only counted while actually hashing, never while starting up "
    "or reconnecting. Payouts depend on your pool's thresholds and luck, so "
    "the fee is 2% of hashing time, not exactly 2% of coins."
)

CSS = """
.hashrate { font-size: 56px; font-weight: 300; font-feature-settings: "tnum"; }
.unit { font-size: 15px; opacity: .55; }
.status-pill { padding: 4px 12px; border-radius: 999px; font-size: 13px;
               background: alpha(currentColor, .08); }
.status-pill.dev { background: alpha(@warning_color, .18); color: @warning_color; }
.status-pill.live { background: alpha(@success_color, .16); color: @success_color; }
.stats { font-feature-settings: "tnum"; font-size: 13px; opacity: .6; }
.mainbtn { min-height: 46px; min-width: 180px; font-size: 16px; }
"""


def _fmt_rate(h):
    if h >= 1e6:
        return f"{h / 1e6:.2f}", "MH/s"
    if h >= 1e3:
        return f"{h / 1e3:.2f}", "kH/s"
    return f"{h:.1f}", "H/s"


def _fmt_time(s):
    s = int(s)
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def load_settings():
    try:
        with open(C.SETTINGS_PATH) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    return {
        "wallet": d.get("wallet", ""),
        "pool": d.get("pool", C.DEFAULT_POOL),
        "tls": bool(d.get("tls", C.DEFAULT_POOL_TLS)),
        "cpu": int(d.get("cpu", 50)),
        "fee_ack": bool(d.get("fee_ack", False)),
    }


def save_settings(s):
    os.makedirs(C.CONFIG_DIR, exist_ok=True)
    tmp = C.SETTINGS_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(s, f, indent=2)
    os.replace(tmp, C.SETTINGS_PATH)


class MonadWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=C.APP_NAME)
        self.set_default_size(420, 640)
        self.settings = load_settings()
        self.miner = Miner(lambda st: GLib.idle_add(self._on_update, st))

        prov = Gtk.CssProvider()
        prov.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.toasts = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title=C.APP_NAME))
        menu = Gtk.MenuButton(icon_name="open-menu-symbolic", tooltip_text="Menu")
        m = Gio.Menu()
        m.append("Developer Fee", "app.fee")
        m.append("About Monad", "app.about")
        menu.set_menu_model(m)
        header.pack_end(menu)
        view.add_top_bar(header)

        clamp = Adw.Clamp(maximum_size=440)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18,
                      margin_top=12, margin_bottom=24, margin_start=16, margin_end=16)
        clamp.set_child(box)
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_child(clamp)
        view.set_content(scroller)
        self.toasts.set_child(view)
        self.set_content(self.toasts)

        # --- readout
        rate_box = Gtk.Box(halign=Gtk.Align.CENTER, spacing=6, margin_top=18)
        self.rate_lbl = Gtk.Label(label="0.0", css_classes=["hashrate"])
        self.unit_lbl = Gtk.Label(label="H/s", css_classes=["unit"], valign=Gtk.Align.BASELINE)
        self.rate_lbl.set_valign(Gtk.Align.BASELINE)
        rate_box.append(self.rate_lbl)
        rate_box.append(self.unit_lbl)
        box.append(rate_box)

        self.status = Gtk.Label(label="Idle", halign=Gtk.Align.CENTER,
                                css_classes=["status-pill"])
        box.append(self.status)
        self.stats = Gtk.Label(label=" ", halign=Gtk.Align.CENTER, css_classes=["stats"])
        box.append(self.stats)

        # --- settings
        group = Adw.PreferencesGroup(margin_top=6)
        self.wallet_row = Adw.EntryRow(title="Your Monero wallet address")
        self.wallet_row.set_text(self.settings["wallet"])
        self.wallet_row.connect("changed", self._validate_wallet)
        group.add(self.wallet_row)

        self.pool_row = Adw.EntryRow(title="Pool (host:port)")
        self.pool_row.set_text(self.settings["pool"])
        group.add(self.pool_row)

        self.tls_row = Adw.SwitchRow(title="TLS", subtitle="Encrypt the pool connection")
        self.tls_row.set_active(self.settings["tls"])
        group.add(self.tls_row)

        adj = Gtk.Adjustment(lower=10, upper=100, step_increment=10, page_increment=10,
                             value=self.settings["cpu"])
        self.cpu_row = Adw.SpinRow(title="CPU usage", subtitle="Percent of threads", adjustment=adj)
        group.add(self.cpu_row)
        box.append(group)

        # --- button
        self.button = Gtk.Button(label="Start", halign=Gtk.Align.CENTER,
                                 css_classes=["pill", "suggested-action", "mainbtn"])
        self.button.connect("clicked", self._on_toggle)
        box.append(self.button)

        fee_btn = Gtk.Button(label="2% of hashing time goes to the developer",
                             halign=Gtk.Align.CENTER, css_classes=["flat", "caption", "dim-label"])
        fee_btn.connect("clicked", lambda *_: self.show_fee_dialog())
        box.append(fee_btn)

        self._validate_wallet(self.wallet_row)
        self.connect("close-request", self._on_close)

    # ----------------------------------------------------------- helpers
    def _inputs(self):
        return {
            "wallet": self.wallet_row.get_text().strip(),
            "pool": self.pool_row.get_text().strip(),
            "tls": self.tls_row.get_active(),
            "cpu": int(self.cpu_row.get_value()),
        }

    def _persist(self):
        self.settings.update(self._inputs())
        save_settings(self.settings)

    def _validate_wallet(self, row):
        text = row.get_text().strip()
        if not text or is_valid_address(text):
            row.remove_css_class("error")
        else:
            row.add_css_class("error")

    def _set_editable(self, on):
        for w in (self.wallet_row, self.pool_row, self.tls_row, self.cpu_row):
            w.set_sensitive(on)

    def _set_status(self, text, kind=None):
        self.status.set_label(text)
        for c in ("dev", "live"):
            self.status.remove_css_class(c)
        if kind:
            self.status.add_css_class(kind)

    def toast(self, msg):
        self.toasts.add_toast(Adw.Toast(title=msg, timeout=4))

    # ------------------------------------------------------------ actions
    def _on_toggle(self, _btn):
        if self.miner.running:
            self.stop_mining()
            return
        s = self._inputs()
        if not is_valid_address(s["wallet"]):
            self.toast("Enter a valid Monero address (starts with 4 or 8)")
            self.wallet_row.grab_focus()
            return
        host, _, port = s["pool"].rpartition(":")
        if not host or not port.isdigit():
            self.toast("Pool must look like host:port")
            return
        if not self.settings.get("fee_ack"):
            self.show_fee_dialog(first_run=True)
            return
        self.start_mining()

    def start_mining(self):
        self._persist()
        try:
            self.miner.start(self.settings)
        except (OSError, FileNotFoundError) as e:
            self.toast(str(e))
            return
        self.button.set_label("Stop")
        self.button.remove_css_class("suggested-action")
        self.button.add_css_class("destructive-action")
        self._set_editable(False)
        self._set_status("Starting…")

    def stop_mining(self):
        self.miner.stop()
        self.button.set_label("Start")
        self.button.remove_css_class("destructive-action")
        self.button.add_css_class("suggested-action")
        self._set_editable(True)
        self._set_status("Idle")
        self.rate_lbl.set_label("0.0")
        self.unit_lbl.set_label("H/s")

    def _on_update(self, st):
        if not self.miner.running and st.get("state") != "crashed":
            return False
        state = st.get("state")
        if state == "crashed":
            tail = [l for l in st.get("log", []) if l.strip()]
            self.stop_mining()
            self._set_status("Miner stopped unexpectedly")
            if tail:
                self.toast(tail[-1][-120:])
            return False
        if state == "starting":
            self._set_status("Preparing RandomX…")
            return False
        num, unit = _fmt_rate(st.get("hashrate", 0))
        self.rate_lbl.set_label(num)
        self.unit_lbl.set_label(unit)
        if st.get("mode") == fee.DEV:
            left = st.get("dev_left", 0)
            self._set_status(f"Developer fee · {_fmt_time(left)} left", "dev")
        elif state == "connecting":
            self._set_status("Connecting…")
        else:
            self._set_status("Mining to your wallet", "live")
        self.stats.set_label(
            f"Shares {st.get('shares', 0)}  ·  Uptime {_fmt_time(st.get('uptime', 0))}")
        return False

    def show_fee_dialog(self, first_run=False):
        d = Adw.AlertDialog(heading="About the developer fee", body=FEE_TEXT)
        if first_run:
            d.add_response("cancel", "Cancel")
            d.add_response("accept", "Accept and Start")
            d.set_response_appearance("accept", Adw.ResponseAppearance.SUGGESTED)
            d.set_default_response("accept")
            d.set_close_response("cancel")

            def done(dlg, res):
                if dlg.choose_finish(res) == "accept":
                    self.settings["fee_ack"] = True
                    self.start_mining()
            d.choose(self, None, done)
        else:
            d.add_response("ok", "OK")
            d.present(self)

    def _on_close(self, *_):
        if self.miner.running:
            self.miner.stop()
        return False

