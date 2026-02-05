
# Splits concatenated JPEG streams inside every .jpg/.jpeg/.bin file in this folder.

import os
import struct

SOI = b"\xFF\xD8"
SOS = 0xDA

# Markers that do NOT have a length field
NO_LEN = set([0xD8, 0xD9] + list(range(0xD0, 0xD8)) + [0x01])  # SOI, EOI, RST0-7, TEM

def _u16be(b: bytes) -> int:
    return struct.unpack(">H", b)[0]

def find_next_soi(data: bytes, start: int = 0) -> int:
    return data.find(SOI, start)

def parse_one_jpeg(data: bytes, start: int) -> int:
    """
    data[start:] begins with SOI. Returns exclusive end offset (right after EOI).
    """
    n = len(data)
    if start < 0 or start + 2 > n or data[start:start+2] != SOI:
        raise ValueError("start is not at SOI")

    i = start + 2
    in_scan = False

    while i < n - 1:
        if data[i] != 0xFF:
            i += 1
            continue

        # Skip fill bytes: FF FF FF ...
        j = i
        while j < n and data[j] == 0xFF:
            j += 1
        if j >= n:
            break

        marker = data[j]

        # In entropy-coded scan data, stuffed 0xFF is FF 00 (not a marker)
        if in_scan and marker == 0x00:
            i = j + 1
            continue

        # Advance past marker byte
        i = j + 1

        # EOI
        if marker == 0xD9:
            return i

        # Start of Scan
        if marker == SOS:
            if i + 2 > n:
                raise ValueError("Truncated SOS length")
            seglen = _u16be(data[i:i+2])
            if seglen < 2:
                raise ValueError("Bad SOS seglen")
            i += seglen
            in_scan = True
            continue

        # Standalone markers
        if marker in NO_LEN:
            continue

        # All other markers have length
        if i + 2 > n:
            raise ValueError("Truncated segment length")
        seglen = _u16be(data[i:i+2])
        if seglen < 2:
            raise ValueError("Bad segment seglen")
        i += seglen

    raise ValueError(f"EOI not found for JPEG starting at 0x{start:X}")

def split_concatenated_jpegs(blob_path: str, out_dir: str) -> int:
    with open(blob_path, "rb") as f:
        data = f.read()

    os.makedirs(out_dir, exist_ok=True)

    pos = 0
    idx = 0
    while True:
        soi = find_next_soi(data, pos)
        if soi < 0:
            break

        try:
            end = parse_one_jpeg(data, soi)
        except ValueError:
            pos = soi + 2
            continue

        out_path = os.path.join(out_dir, f"img_{idx:04d}.jpg")
        with open(out_path, "wb") as o:
            o.write(data[soi:end])

        idx += 1
        pos = end

    return idx

def main():
    here = os.path.abspath(os.path.dirname(__file__))

    exts = {".jpg", ".jpeg", ".bin"}
    files = [
        f for f in os.listdir(here)
        if os.path.isfile(os.path.join(here, f)) and os.path.splitext(f)[1].lower() in exts
    ]

    if not files:
        print("No .jpg/.jpeg/.bin files found in this directory.")
        return

    for fname in sorted(files):
        in_path = os.path.join(here, fname)
        base = os.path.splitext(fname)[0]
        out_dir = os.path.join(here, f"split_{base}")

        count = split_concatenated_jpegs(in_path, out_dir)

        if count == 0:
            try:
                os.rmdir(out_dir)
            except OSError:
                pass
            print(f"[{fname}] no JPEG streams found")
        else:
            print(f"[{fname}] extracted {count} JPEG(s) -> {os.path.basename(out_dir)}\\")

if __name__ == "__main__":
    main()
