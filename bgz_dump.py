# Extracts pointer-defined blocks from a BGZ into individual files.
# - Reads N 32-bit pointers from a table
# - Computes sizes from next pointer (or EOF for last)
# - Writes each block to out_dir as block_XXXX_<ofs>_<size>.<ext>

import os
import struct
from dataclasses import dataclass
from typing import List, Optional

# ----------------------------
# Helpers
# ----------------------------

def read_u32(f, endian: str) -> int:
    b = f.read(4)
    if len(b) != 4:
        raise EOFError("Unexpected EOF while reading u32")
    if endian == "be":
        return struct.unpack(">I", b)[0]
    if endian == "le":
        return struct.unpack("<I", b)[0]
    raise ValueError("endian must be 'be' or 'le'")

def fmt_hex(n: int) -> str:
    return f"0x{n:08X}"

def within(n: int, lo: int, hi: int) -> bool:
    return lo <= n < hi

def detect_ext(first16: bytes) -> str:
    # JPEG
    if len(first16) >= 3 and first16[0] == 0xFF and first16[1] == 0xD8 and first16[2] == 0xFF:
        return "jpg"
    # ASCII signatures (e.g. "shd.")
    if first16.startswith(b"shd."):
        return "shd"
    # JFIF/Exif typically comes after FF D8 FF E0/E1, handled by JPEG case
    return "bin"

# ----------------------------
# Data
# ----------------------------

@dataclass
class Block:
    index: int
    ofs: int
    size: int
    ext: str
    note: str = ""

# ----------------------------
# Core
# ----------------------------

def read_pointer_blocks(
    path: str,
    table_offset: int,
    count: int,
    endian: str = "be",
    base: int = 0,
    require_monotonic: bool = True,
) -> List[Block]:
    file_size = os.path.getsize(path)

    # read raw pointers
    ptrs: List[int] = []
    with open(path, "rb") as f:
        f.seek(table_offset)
        for _ in range(count):
            ptrs.append(read_u32(f, endian))

    # abs offsets
    abs_ptrs = [base + p for p in ptrs]

    blocks: List[Block] = []
    with open(path, "rb") as f:
        for i, ofs in enumerate(abs_ptrs):
            if not within(ofs, 0, file_size):
                blocks.append(Block(i, ofs, 0, "bin", "OUT_OF_RANGE"))
                continue

            # size by next pointer or EOF
            if i < len(abs_ptrs) - 1:
                nxt = abs_ptrs[i + 1]
                if nxt < ofs:
                    if require_monotonic:
                        blocks.append(Block(i, ofs, 0, "bin", "NON_MONOTONIC_NEXT_PTR"))
                        continue
                    # fallback: size unknown, skip
                    blocks.append(Block(i, ofs, 0, "bin", "NON_MONOTONIC_NEXT_PTR"))
                    continue
                size = nxt - ofs
            else:
                size = file_size - ofs

            # sanity
            if size <= 0 or (ofs + size) > file_size:
                blocks.append(Block(i, ofs, 0, "bin", "BAD_SIZE"))
                continue

            # detect extension by signature
            f.seek(ofs)
            sig = f.read(16)
            ext = detect_ext(sig)

            blocks.append(Block(i, ofs, size, ext, ""))

    return blocks

def extract_blocks(
    path: str,
    blocks: List[Block],
    out_dir: str,
    overwrite: bool = False,
    skip_zero: bool = True,
) -> None:
    os.makedirs(out_dir, exist_ok=True)

    with open(path, "rb") as f:
        for b in blocks:
            if skip_zero and b.size == 0:
                print(f"[SKIP] {b.index:04d} ofs={fmt_hex(b.ofs)} size=0 note={b.note}")
                continue

            name = f"block_{b.index:04d}_{b.ofs:08X}_{b.size:08X}.{b.ext}"
            out_path = os.path.join(out_dir, name)

            if (not overwrite) and os.path.exists(out_path):
                print(f"[SKIP] exists: {out_path}")
                continue

            f.seek(b.ofs)
            data = f.read(b.size)

            with open(out_path, "wb") as out:
                out.write(data)

            note = f" note={b.note}" if b.note else ""
            print(f"[OK]   {b.index:04d} -> {name} ({b.size} bytes){note}")

def print_blocks(blocks: List[Block]) -> None:
    print("Index | Offset       | Size         | Ext | Note")
    print("------+--------------+--------------+-----+----------------")
    for b in blocks:
        print(f"{b.index:5d} | {fmt_hex(b.ofs)} | {fmt_hex(b.size)} | {b.ext:3s} | {b.note}")

# ----------------------------
# Configure + run
# ----------------------------

if __name__ == "__main__":
    # Set these:
    BGZ_PATH     = r"r111.bgz"       # or full path
    TABLE_OFFSET = 0x00              # where the pointer table begins
    COUNT        = 5                 # you choose 
    ENDIAN       = "be"              # Big Endian for GX
    BASE         = 0                 # adjust if pointers are relative
    OUT_DIR      = r"dump_blocks"    # folder to write extracted blocks

    if not os.path.exists(BGZ_PATH):
        raise FileNotFoundError(f"File not found: {BGZ_PATH}")

    blocks = read_pointer_blocks(
        BGZ_PATH,
        table_offset=TABLE_OFFSET,
        count=COUNT,
        endian=ENDIAN,
        base=BASE,
        require_monotonic=True
    )

    print_blocks(blocks)
    print()
    extract_blocks(BGZ_PATH, blocks, OUT_DIR, overwrite=False, skip_zero=True)
