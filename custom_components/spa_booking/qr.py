"""QR codes in pure Python (3.2.0): byte mode, error correction M, versions
1-10 (up to 213 bytes, plenty for a booking link), as a matrix, an SVG or
a PNG — no library needed, in Home Assistant or Spa Booking Web.
"""

from __future__ import annotations

import struct
import zlib

# version: (ec codewords per block, [(blocks, data codewords per block), ...])
_EC_M = {
    1: (10, [(1, 16)]), 2: (16, [(1, 28)]), 3: (26, [(1, 44)]), 4: (18, [(2, 32)]),
    5: (24, [(2, 43)]), 6: (16, [(4, 27)]), 7: (18, [(4, 31)]), 8: (22, [(2, 38), (2, 39)]),
    9: (22, [(3, 36), (2, 37)]), 10: (26, [(4, 43), (1, 44)]),
}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34],
          7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50]}

_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _gf_mul(a: int, b: int) -> int:
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def _rs_generator(degree: int) -> list[int]:
    poly = [1]
    for i in range(degree):
        nxt = [0] * (len(poly) + 1)
        for j, coef in enumerate(poly):
            nxt[j] ^= coef
            nxt[j + 1] ^= _gf_mul(coef, _EXP[i])
        poly = nxt
    return poly


def _rs_remainder(data: list[int], degree: int) -> list[int]:
    gen = _rs_generator(degree)
    rem = [0] * degree
    for byte in data:
        factor = byte ^ rem[0]
        rem = rem[1:] + [0]
        for i in range(degree):
            rem[i] ^= _gf_mul(gen[i + 1], factor)
    return rem


def _capacity(version: int) -> int:
    return sum(blocks * size for blocks, size in _EC_M[version][1])


def _codewords(data: bytes) -> tuple[int, list[int]]:
    for version in range(1, 11):
        count_bits = 8 if version < 10 else 16
        if 4 + count_bits + 8 * len(data) <= 8 * _capacity(version):
            break
    else:
        raise ValueError("Testo troppo lungo per il codice QR")
    bits: list[int] = []

    def put(value: int, length: int) -> None:
        bits.extend((value >> (length - 1 - i)) & 1 for i in range(length))

    put(0b0100, 4)
    put(len(data), count_bits)
    for byte in data:
        put(byte, 8)
    total = 8 * _capacity(version)
    put(0, min(4, total - len(bits)))
    while len(bits) % 8:
        bits.append(0)
    codewords = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = (0xEC, 0x11)
    while len(codewords) < _capacity(version):
        codewords.append(pad[(len(codewords) - len(bits) // 8) % 2])
    ec_len, groups = _EC_M[version]
    blocks: list[list[int]] = []
    pos = 0
    for count, size in groups:
        for _ in range(count):
            blocks.append(codewords[pos:pos + size])
            pos += size
    ecs = [_rs_remainder(block, ec_len) for block in blocks]
    out: list[int] = []
    for i in range(max(len(b) for b in blocks)):
        out.extend(b[i] for b in blocks if i < len(b))
    for i in range(ec_len):
        out.extend(e[i] for e in ecs)
    return version, out


def _bch(value: int, poly: int, poly_len: int) -> int:
    value <<= poly_len - 1
    while value.bit_length() >= poly_len:
        value ^= poly << (value.bit_length() - poly_len)
    return value


_MASKS = [
    lambda r, c: (r + c) % 2 == 0,
    lambda r, c: r % 2 == 0,
    lambda r, c: c % 3 == 0,
    lambda r, c: (r + c) % 3 == 0,
    lambda r, c: (r // 2 + c // 3) % 2 == 0,
    lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
    lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
    lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
]


def _penalty(m: list[list[bool]]) -> int:
    n = len(m)
    score = 0
    for grid in (m, [list(col) for col in zip(*m, strict=True)]):
        for row in grid:
            run = 1
            for i in range(1, n):
                if row[i] == row[i - 1]:
                    run += 1
                else:
                    if run >= 5:
                        score += run - 2
                    run = 1
            if run >= 5:
                score += run - 2
            line = "".join("1" if v else "0" for v in row)
            score += 40 * (line.count("10111010000") + line.count("00001011101"))
    for r in range(n - 1):
        for c in range(n - 1):
            if m[r][c] == m[r][c + 1] == m[r + 1][c] == m[r + 1][c + 1]:
                score += 3
    dark = sum(v for row in m for v in row)
    score += 10 * (abs(dark * 20 - n * n * 10) // (n * n))
    return score


def qr_matrix(text: str) -> list[list[bool]]:
    """The modules of the QR code of ``text`` (True = dark), no quiet zone."""
    version, data = _codewords(text.encode("utf-8"))
    n = 17 + 4 * version
    grid: list[list[bool | None]] = [[None] * n for _ in range(n)]
    reserved = [[False] * n for _ in range(n)]

    def setm(r: int, c: int, dark: bool) -> None:
        grid[r][c] = dark
        reserved[r][c] = True

    for (r0, c0) in ((0, 0), (0, n - 7), (n - 7, 0)):
        for r in range(-1, 8):
            for c in range(-1, 8):
                rr, cc = r0 + r, c0 + c
                if 0 <= rr < n and 0 <= cc < n:
                    dark = (0 <= r <= 6 and c in (0, 6)) or (0 <= c <= 6 and r in (0, 6)) or (2 <= r <= 4 and 2 <= c <= 4)
                    setm(rr, cc, dark)
    for i in range(8, n - 8):
        setm(6, i, i % 2 == 0)
        setm(i, 6, i % 2 == 0)
    centres = _ALIGN[version]
    for r in centres:
        for c in centres:
            if (r, c) in ((centres[0], centres[0]), (centres[0], centres[-1]), (centres[-1], centres[0])):
                continue  # under a finder pattern
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    setm(r + dr, c + dc, max(abs(dr), abs(dc)) != 1)
    setm(n - 8, 8, True)  # the dark module
    for i in range(9):  # format areas
        for (r, c) in ((8, i), (i, 8)):
            if not reserved[r][c]:
                reserved[r][c] = True
    for i in range(8):
        reserved[8][n - 1 - i] = True
        reserved[n - 1 - i][8] = True
    if version >= 7:
        info = (version << 12) | _bch(version, 0x1F25, 13)
        for i in range(18):
            dark = bool((info >> i) & 1)
            setm(i // 3, n - 11 + i % 3, dark)
            setm(n - 11 + i % 3, i // 3, dark)

    bits = [(byte >> (7 - i)) & 1 for byte in data for i in range(8)]
    index = 0
    col = n - 1
    upward = True
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(n - 1, -1, -1) if upward else range(n)
        for r in rows:
            for c in (col, col - 1):
                if not reserved[r][c]:
                    grid[r][c] = bool(bits[index]) if index < len(bits) else False
                    index += 1
        upward = not upward
        col -= 2

    best: list[list[bool]] | None = None
    best_score = None
    for mask_id, mask in enumerate(_MASKS):
        m = [[bool(grid[r][c]) ^ (not reserved[r][c] and mask(r, c)) for c in range(n)] for r in range(n)]
        fmt = (0b00 << 3) | mask_id  # error correction M
        fmt = ((fmt << 10) | _bch(fmt, 0x537, 11)) ^ 0x5412
        for i in range(15):
            dark = bool((fmt >> i) & 1)
            # First copy, around the top-left finder.
            if i < 6:
                m[i][8] = dark
            elif i == 6:
                m[7][8] = dark
            elif i == 7:
                m[8][8] = dark
            elif i == 8:
                m[8][7] = dark
            else:
                m[8][14 - i] = dark
            # Second copy, split between the other two finders.
            if i < 8:
                m[8][n - 1 - i] = dark
            else:
                m[n - 15 + i][8] = dark
        m[n - 8][8] = True
        score = _penalty(m)
        if best_score is None or score < best_score:
            best, best_score = m, score
    assert best is not None
    return best


def qr_svg(text: str, size: int = 200, dark: str = "#000", light: str = "#fff", border: int = 4) -> str:
    matrix = qr_matrix(text)
    n = len(matrix) + 2 * border
    path = "".join(f"M{c + border},{r + border}h1v1h-1z" for r, row in enumerate(matrix) for c, v in enumerate(row) if v)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" width="{size}" height="{size}" '
            f'shape-rendering="crispEdges"><rect width="{n}" height="{n}" fill="{light}"/>'
            f'<path d="{path}" fill="{dark}"/></svg>')


def qr_png(text: str, scale: int = 8, border: int = 4, dark: tuple[int, int, int] = (0, 0, 0)) -> bytes:
    """A PNG (palette, 1 bit) of the QR code: fit for e-mails, where SVG is not."""
    matrix = qr_matrix(text)
    n = len(matrix) + 2 * border
    side = n * scale
    rows = []
    for r in range(n):
        line = []
        for c in range(n):
            mr, mc = r - border, c - border
            on = 0 <= mr < len(matrix) and 0 <= mc < len(matrix) and matrix[mr][mc]
            line.extend([1 if on else 0] * scale)
        packed = bytearray([0])
        for i in range(0, side, 8):
            byte = 0
            for j, bit in enumerate(line[i:i + 8]):
                byte |= bit << (7 - j)
            packed.append(byte)
        rows.extend([bytes(packed)] * scale)

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", side, side, 1, 3, 0, 0, 0))
            + chunk(b"PLTE", bytes((255, 255, 255)) + bytes(dark))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))
