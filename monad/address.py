# SPDX-License-Identifier: GPL-3.0-or-later
"""Monero address validation (Monero base58 + Keccak-256 checksum).

Monero uses the original Keccak-256 (padding byte 0x01), which is *not*
hashlib.sha3_256 (padding 0x06), so a tiny pure-Python Keccak is included.
"""

_RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]
_ROT = [
    [0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61],
    [28, 55, 25, 21, 56], [27, 20, 39, 8, 14],
]
_M = (1 << 64) - 1


def _rol(x, n):
    return ((x << n) | (x >> (64 - n))) & _M if n else x


def _f(s):
    for rc in _RC:
        c = [s[x][0] ^ s[x][1] ^ s[x][2] ^ s[x][3] ^ s[x][4] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rol(c[(x + 1) % 5], 1) for x in range(5)]
        s = [[s[x][y] ^ d[x] for y in range(5)] for x in range(5)]
        b = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                b[y][(2 * x + 3 * y) % 5] = _rol(s[x][y], _ROT[x][y])
        s = [[b[x][y] ^ (~b[(x + 1) % 5][y] & b[(x + 2) % 5][y]) for y in range(5)]
             for x in range(5)]
        s[0][0] ^= rc
    return s


def keccak256(data: bytes) -> bytes:
    rate = 136
    msg = bytearray(data) + b"\x01"
    msg += b"\x00" * (-len(msg) % rate)
    msg[-1] |= 0x80
    s = [[0] * 5 for _ in range(5)]
    for off in range(0, len(msg), rate):
        block = msg[off:off + rate]
        for i in range(rate // 8):
            x, y = i % 5, i // 5
            s[x][y] ^= int.from_bytes(block[8 * i:8 * i + 8], "little")
        s = _f(s)
    out = b"".join(s[i % 5][i // 5].to_bytes(8, "little") for i in range(4))
    return out


_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_IDX = {c: i for i, c in enumerate(_ALPHABET)}
_ENC_BLOCK = [0, 2, 3, 5, 6, 7, 9, 10, 11]  # bytes -> chars


def _b58decode(s: str) -> bytes:
    out = bytearray()
    full, rem = divmod(len(s), 11)
    chunks = [s[i * 11:(i + 1) * 11] for i in range(full)]
    if rem:
        chunks.append(s[full * 11:])
    for chunk in chunks:
        if len(chunk) not in _ENC_BLOCK:
            raise ValueError("bad length")
        nbytes = _ENC_BLOCK.index(len(chunk))
        num = 0
        for ch in chunk:
            num = num * 58 + _IDX[ch]
        if num >= 1 << (8 * nbytes):
            raise ValueError("overflow")
        out += num.to_bytes(nbytes, "big")
    return bytes(out)


# Mainnet network bytes: standard, integrated, subaddress
_MAINNET = {18: "standard", 19: "integrated", 42: "subaddress"}


def address_kind(addr: str):
    """Return 'standard' / 'subaddress' / 'integrated' for a valid mainnet
    Monero address, or None if it is not valid."""
    addr = (addr or "").strip()
    if len(addr) not in (95, 106) or any(c not in _IDX for c in addr):
        return None
    try:
        raw = _b58decode(addr)
    except (ValueError, KeyError):
        return None
    body, checksum = raw[:-4], raw[-4:]
    if keccak256(body)[:4] != checksum:
        return None
    kind = _MAINNET.get(body[0])
    if kind is None:
        return None
    expected = 1 + 64 + (8 if kind == "integrated" else 0)
    return kind if len(body) == expected else None


def is_valid_address(addr: str) -> bool:
    return address_kind(addr) is not None
