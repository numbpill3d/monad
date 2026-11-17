# SPDX-License-Identifier: GPL-3.0-or-later
"""XMRig process controller.

Runs a bundled XMRig (built with its own donation disabled) with a private
HTTP API bound to 127.0.0.1 and protected by a random token.  The developer
fee is applied by live-reloading the pool list through that API, which
reconnects the pool without re-initialising RandomX.
"""
import collections
import ctypes
import json
import os
import secrets
import signal
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request

from . import constants as C
from . import fee

POLL_SECONDS = 2.0
SAVE_EVERY = 30.0


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _child_setup():
    # Die with the parent (no orphaned miners) and stay out of the desktop's way.
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG
    except OSError:
        pass
    try:
        os.nice(10)
    except OSError:
        pass


class Miner:
    """Thread-based controller.  `on_update(state: dict)` is called from a
    worker thread; GUI code must marshal it to the main loop."""

    def __init__(self, on_update):
        self.on_update = on_update
        self.proc = None
        self.log = collections.deque(maxlen=300)
        self.scheduler = fee.FeeScheduler(fee.load_ledger(C.LEDGER_PATH))
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self.settings = {}

    # ---------------------------------------------------------------- config
    def _pool(self, mode):
        s = self.settings
        if mode == fee.DEV:
            url, tls, user = C.DEV_POOL, C.DEV_POOL_TLS, C.DEV_WALLET
            password = "monad-devfee"
        else:
            url, tls, user = s["pool"], s["tls"], s["wallet"]
            password = s.get("worker") or "monad"
        return {
            "url": url, "user": user, "pass": password, "tls": tls,
            "keepalive": True, "algo": "rx/0", "enabled": True, "nicehash": False,
        }

    def _config(self, mode):
        return {
            "api": {"id": None, "worker-id": "monad"},
            "http": {
                "enabled": True, "host": "127.0.0.1", "port": self.port,
                "access-token": self.token, "restricted": False,
            },
            "autosave": False,
            "background": False,
            "colors": False,
            "title": False,
            "donate-level": 0,
            "donate-over-proxy": 0,
            "randomx": {"init": -1, "mode": "auto", "1gb-pages": False,
                        "rdmsr": False, "wrmsr": False, "numa": True},
            "cpu": {"enabled": True, "huge-pages": True, "huge-pages-jit": False,
                    "max-threads-hint": int(self.settings["cpu"]), "yield": True},
            "opencl": False,
            "cuda": False,
            "pools": [self._pool(mode)],
            "print-time": 60,
            "health-print-time": 0,
            "retries": 5,
            "retry-pause": 5,
            "syslog": False,
            "user-agent": None,
            "verbose": 0,
            "watch": False,
            "pause-on-battery": False,
            "pause-on-active": False,
        }

    # ------------------------------------------------------------------- api
    def _api(self, method, path, body=None, timeout=3):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data, method=method,
            headers={"Authorization": f"Bearer {self.token}",
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}

    # ------------------------------------------------------------- lifecycle
    @property
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self, settings):
        if self.running:
            return
        binary = C.find_xmrig()
        if not binary:
            raise FileNotFoundError("The bundled XMRig miner was not found.")
        self.settings = dict(settings)
        self.port = _free_port()
        self.token = secrets.token_hex(24)
        self.scheduler.reset_session()
        self.mode = fee.USER
        self.switched_at = time.monotonic()

        rundir = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or C.STATE_DIR, "monad")
        os.makedirs(rundir, mode=0o700, exist_ok=True)
        self.cfg_path = os.path.join(rundir, "xmrig.json")
        fd = os.open(self.cfg_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(self._config(self.mode), f)

        self.log.clear()
        self.proc = subprocess.Popen(
            [binary, f"--config={self.cfg_path}", "--no-color"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            text=True, bufsize=1, preexec_fn=_child_setup)
        self._stop.clear()
        threading.Thread(target=self._read_output, daemon=True).start()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        proc = self.proc
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)
        with self._lock:
            self.scheduler.reset_session()
            fee.save_ledger(C.LEDGER_PATH, self.scheduler.ledger)
        try:
            os.unlink(self.cfg_path)
        except (OSError, AttributeError):
            pass

    def _read_output(self):
        proc = self.proc
        for line in proc.stdout:
            self.log.append(line.rstrip())

    # ------------------------------------------------------------ main loop
    def _switch(self, mode):
        try:
            self._api("PUT", "/1/config", self._config(mode))
        except (urllib.error.URLError, OSError, ValueError) as e:
            self.log.append(f"[monad] pool switch failed: {e}")
            return False
        self.mode = mode
        self.switched_at = time.monotonic()
        self.log.append(f"[monad] switched to {'developer fee' if mode == fee.DEV else 'user'} pool")
        return True

    def _loop(self):
        last = time.monotonic()
        last_save = last
        while not self._stop.wait(POLL_SECONDS):
            now = time.monotonic()
            dt, last = now - last, now
            if self._stop.is_set():
                return
            if not self.running:
                code = self.proc.returncode if self.proc else None
                self.on_update({"state": "crashed", "code": code,
                                "log": list(self.log)[-8:]})
                with self._lock:
                    fee.save_ledger(C.LEDGER_PATH, self.scheduler.ledger)
                return
            try:
                summ = self._api("GET", "/2/summary")
            except (urllib.error.URLError, OSError, ValueError):
                self.on_update({"state": "starting", "mode": self.mode})
                continue

            conn = summ.get("connection", {}) or {}
            hr = (summ.get("hashrate", {}) or {}).get("total", []) or []
            rate = next((h for h in hr if h), 0.0) or 0.0
            uptime = conn.get("uptime", 0) or 0
            since_switch = now - self.switched_at
            # Only bill time on a connection opened after the last switch.
            fresh = uptime > 0 and uptime <= since_switch + POLL_SECONDS + 1
            hashing = bool(rate > 0 and fresh)

            with self._lock:
                want = self.scheduler.tick(dt, hashing)
                if want != self.mode:
                    if not self._switch(want):
                        self.scheduler.mode = self.mode
                if now - last_save >= SAVE_EVERY:
                    fee.save_ledger(C.LEDGER_PATH, self.scheduler.ledger)
                    last_save = now

            res = summ.get("results", {}) or {}
            self.on_update({
                "state": "mining" if hashing else "connecting",
                "mode": self.mode,
                "hashrate": rate,
                "shares": res.get("shares_good", 0),
                "uptime": summ.get("uptime", 0),
                "dev_left": self.scheduler.dev_seconds_left,
                "pool": conn.get("pool", ""),
                "hugepages": (summ.get("hugepages") or [0, 0]),
            })
