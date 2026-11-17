# SPDX-License-Identifier: GPL-3.0-or-later
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from monad.address import address_kind, is_valid_address, keccak256  # noqa: E402
from monad.constants import DEV_WALLET  # noqa: E402
from monad import fee  # noqa: E402

EXPECTED_DEV = ("49PHjHqpnRSdZxFgaEyhyzVBbiD8nbV3XVBdEequwaisidKejyZ8wti5"
                "jLhRUk9yq1ZS3wFpTk3vS97Gu2fBi19xD9NGdMn")


class AddressTests(unittest.TestCase):
    def test_keccak_vectors(self):
        # Original Keccak-256 (not SHA3-256)
        self.assertEqual(keccak256(b"").hex(),
                         "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")
        self.assertEqual(keccak256(b"abc").hex(),
                         "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45")
        self.assertEqual(keccak256(b"a" * 300).hex(), keccak256(b"a" * 300).hex())

    def test_dev_wallet_constant(self):
        self.assertEqual(DEV_WALLET, EXPECTED_DEV)
        self.assertEqual(address_kind(DEV_WALLET), "standard")

    def test_rejects_garbage(self):
        self.assertFalse(is_valid_address(""))
        self.assertFalse(is_valid_address("hello"))
        self.assertFalse(is_valid_address(DEV_WALLET[:-1] + ("o" if DEV_WALLET[-1] != "o" else "p")))
        flipped = DEV_WALLET[:10] + ("A" if DEV_WALLET[10] != "A" else "B") + DEV_WALLET[11:]
        self.assertFalse(is_valid_address(flipped))
        self.assertFalse(is_valid_address(DEV_WALLET + "1"))


class FeeTests(unittest.TestCase):
    def run_sim(self, sched, seconds, dt=1.0, hashing=True):
        for _ in range(int(seconds / dt)):
            sched.tick(dt, hashing)

    def test_long_run_ratio_is_two_percent(self):
        s = fee.FeeScheduler()
        self.run_sim(s, 10 * 3600)
        self.assertAlmostEqual(s.ledger.ratio, 0.02, delta=0.002)

    def test_starts_on_user_pool(self):
        s = fee.FeeScheduler()
        self.assertEqual(s.tick(1, True), fee.USER)

    def test_no_billing_while_not_hashing(self):
        s = fee.FeeScheduler()
        self.run_sim(s, 3600, hashing=False)
        self.assertEqual(s.ledger.user_seconds + s.ledger.dev_seconds, 0)

    def test_slice_cadence(self):
        s = fee.FeeScheduler()
        switches = []
        prev = s.mode
        for t in range(6 * 3600):
            m = s.tick(1, True)
            if m != prev:
                switches.append((t, m))
                prev = m
        dev_starts = [t for t, m in switches if m == fee.DEV]
        # about one slice every ~49 minutes
        self.assertTrue(6 <= len(dev_starts) <= 8, dev_starts)
        self.assertGreater(dev_starts[0], 45 * 60)

    def test_stop_restart_short_sessions_still_pay(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "ledger.json")
            # 300 sessions of 2 minutes each, with a reload from disk between
            # them, and a stop in the middle of a dev slice now and then.
            for _ in range(300):
                s = fee.FeeScheduler(fee.load_ledger(path))
                self.run_sim(s, 120)
                s.reset_session()
                fee.save_ledger(path, s.ledger)
            led = fee.load_ledger(path)
            self.assertAlmostEqual(led.ratio, 0.02, delta=0.003)

    def test_partial_dev_slice_is_credited(self):
        s = fee.FeeScheduler(fee.Ledger(user_seconds=50 * 60 * 1.0, dev_seconds=0))
        self.assertEqual(s.tick(1, True), fee.DEV)
        self.run_sim(s, 20)
        s.reset_session()
        self.assertAlmostEqual(s.ledger.dev_seconds, 20, delta=1)
        self.assertEqual(s.mode, fee.USER)
        # next session resumes the remaining debt as soon as it is >= slice
        self.assertGreater(s.ledger.debt, 0)

    def test_unreachable_dev_pool_falls_back_to_user(self):
        s = fee.FeeScheduler(fee.Ledger(user_seconds=3000, dev_seconds=0))
        self.assertEqual(s.tick(1, True), fee.DEV)
        debt = s.ledger.debt
        for _ in range(120):          # dev pool never connects
            s.tick(1, False)
        self.assertEqual(s.mode, fee.USER)
        self.assertAlmostEqual(s.ledger.debt, debt, delta=0.01)
        self.run_sim(s, 300)          # backoff: keeps mining for the user
        self.assertEqual(s.mode, fee.USER)
        modes = [s.tick(1, True) for _ in range(400)]   # then retries the slice
        self.assertIn(fee.DEV, modes)


class RoutingTests(unittest.TestCase):
    def test_config_routes_shares(self):
        from monad.miner import Miner
        from monad import constants as C
        user_wallet = "4" + "A" * 94
        m = Miner(lambda st: None)
        m.port, m.token = 1, "t"
        m.settings = {"wallet": user_wallet, "pool": "p2pool.local:3333",
                      "tls": False, "cpu": 50}
        u = m._config(fee.USER)
        d = m._config(fee.DEV)
        self.assertEqual(u["pools"][0]["user"], user_wallet)
        self.assertEqual(u["pools"][0]["url"], "p2pool.local:3333")
        self.assertEqual(d["pools"][0]["user"], C.DEV_WALLET)
        self.assertEqual(d["pools"][0]["url"], C.DEV_POOL)
        self.assertTrue(d["pools"][0]["tls"])
        for c in (u, d):
            self.assertEqual(c["donate-level"], 0)
            self.assertEqual(len(c["pools"]), 1)
            self.assertEqual(c["http"]["host"], "127.0.0.1")
            self.assertEqual(c["cpu"], u["cpu"])   # no worker restart on switch
            self.assertEqual(c["randomx"], u["randomx"])


if __name__ == "__main__":
    unittest.main()
