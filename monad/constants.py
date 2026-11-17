# SPDX-License-Identifier: GPL-3.0-or-later
import os

APP_ID = "io.github.numbpill3d.Monad"
APP_NAME = "Monad"
VERSION = "1.0.0"
WEBSITE = "https://github.com/numbpill3d/monad"
ISSUES = "https://github.com/numbpill3d/monad/issues"

# --- Developer fee (disclosed in the UI, README and AppStream metadata) ---
# 2% of hashing time is mined to this wallet on a fixed pool, independent of
# the pool the user chooses, so the fee works the same with any pool.
DEV_WALLET = (
    "49PHjHqpnRSdZxFgaEyhyzVBbiD8nbV3XVBdEequwaisidKejyZ8wti5jLhRUk9yq1ZS3wFpTk3vS97Gu2fBi19xD9NGdMn"
)
DEV_POOL = "pool.supportxmr.com:443"
DEV_POOL_TLS = True

DEFAULT_POOL = "pool.supportxmr.com:443"
DEFAULT_POOL_TLS = True

XMRIG_CANDIDATES = [
    os.environ.get("MONAD_XMRIG", ""),
    "/app/libexec/monad/xmrig",
    "/usr/lib/monad/xmrig",
    "/usr/libexec/monad/xmrig",
    "/usr/local/libexec/monad/xmrig",
]


def _xdg(var, fallback):
    return os.environ.get(var) or os.path.expanduser(fallback)


CONFIG_DIR = os.path.join(_xdg("XDG_CONFIG_HOME", "~/.config"), "monad")
STATE_DIR = os.path.join(_xdg("XDG_STATE_HOME", "~/.local/state"), "monad")
SETTINGS_PATH = os.path.join(CONFIG_DIR, "settings.json")
LEDGER_PATH = os.path.join(STATE_DIR, "fee-ledger.json")


def find_xmrig():
    for p in XMRIG_CANDIDATES:
        if p and os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None
