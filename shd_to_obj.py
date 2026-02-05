
#   rec+0x00 = rel offset to float3 list (usually 0x10)
#   rec+0x04 = boundary/end of that float list (file offset, e.g. 0x09DC)
# Then finds the u16 triangle list (00 00 00 01 00 02 ...) and exports OBJ.
#
# Tested against your uploaded file layout.

import os
import struct

def u32be(d, o): return struct.unpack_from(">I", d, o)[0]
def u16be(d, o): return struct.unpack_from(">H", d, o)[0]
def f32be(d, o): return struct.unpack_from(">f", d, o)[0]

def find_first_record(d: bytes, ofs_desc: int) -> int:
    # table starts with zeros; record begins at first non-zero u32
    for off in range(ofs_desc, min(ofs_desc + 0x200, len(d) - 16), 4):
        if u32be(d, off) != 0:
            return off
    return -1

def find_bytes(d: bytes, pat: bytes, start: int, end: int) -> int:
    i = d.find(pat, start, end)
    return i

def dump_obj(shd_path: str, out_obj: str):
    d = open(shd_path, "rb").read()
    size = len(d)

    ofs_desc = u32be(d, 0x38)  # 0x40
    ofs_mark = u32be(d, 0x3C)  # Varies start of TPL (used as end marker only)

    rec = find_first_record(d, ofs_desc)
    if rec < 0:
        raise ValueError("Could not locate descriptor record")

    rel_floats = u32be(d, rec + 0x00)     # 0x10 (relative)
    next_ofs   = u32be(d, rec + 0x04)     # 0x09DC (boundary/end)
    floats_ofs = rec + rel_floats

    if not (0 <= floats_ofs < size) or not (0 <= next_ofs <= size):
        raise ValueError("Offsets out of range")
    if next_ofs <= floats_ofs:
        raise ValueError("next_ofs must be > floats_ofs")

    # Vertices are float3 packed from floats_ofs..next_ofs
    vert_bytes = next_ofs - floats_ofs
    if vert_bytes % 12 != 0:
        raise ValueError(f"Float block size not multiple of 12 (got {vert_bytes})")
    vert_count = vert_bytes // 12

    # Find index run after next_ofs, before marker
    pat = b"\x00\x00\x00\x01\x00\x02"
    search_end = min(ofs_mark, size)
    idx_start = find_bytes(d, pat, next_ofs, search_end)
    if idx_start < 0:
        raise ValueError("Could not find index run (00 00 00 01 00 02) after next_ofs")

    # Read vertices
    verts = []
    for i in range(vert_count):
        off = floats_ofs + i * 12
        x = f32be(d, off + 0)
        y = f32be(d, off + 4)
        z = f32be(d, off + 8)
        verts.append((x, y, z))

    # Read indices (u16) until marker
    indices = []
    for off in range(idx_start, search_end, 2):
        indices.append(u16be(d, off))

    # Build faces (triangle list)
    faces = []
    for t in range(0, len(indices) - 2, 3):
        a, b, c = indices[t], indices[t + 1], indices[t + 2]
        if a < vert_count and b < vert_count and c < vert_count:
            faces.append((a, b, c))

    # Write OBJ
    with open(out_obj, "w", newline="\n") as f:
        f.write(f"# {os.path.basename(shd_path)}\n")
        f.write(f"# rec=0x{rec:X} floats_ofs=0x{floats_ofs:X} next_ofs=0x{next_ofs:X}\n")
        f.write(f"# vert_count={vert_count} idx_start=0x{idx_start:X} idx_end=0x{search_end:X}\n")
        f.write("o shd_mesh\n")
        for x, y, z in verts:
            f.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
        for a, b, c in faces:
            a += 1; b += 1; c += 1
            f.write(f"f {a} {b} {c}\n")

    print("Wrote:", out_obj)
    print(f"Vertices: {vert_count} (from 0x{floats_ofs:X}..0x{next_ofs:X})")
    print(f"Faces:    {len(faces)} (indices from 0x{idx_start:X}..0x{search_end:X})")

if __name__ == "__main__":
    SHD_PATH = r"block_0003_000098E0_00007540.shd"
    OUT_OBJ  = r"block_0003_000098E0_00007540.obj"
    dump_obj(SHD_PATH, OUT_OBJ)
