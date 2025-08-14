from dataclasses import dataclass
from pathlib import Path
from io import BytesIO
from typing import List
import struct
import gzip
import argparse
from lxml import etree as ET


# Standalone applier for FaceChat/NPC translated XML -> .scr inside .arc


def get_string_at(f, addr: int, encoding: str = "ascii") -> str:
    pos = f.tell()
    f.seek(addr)
    s = b""
    while True:
        c = f.read(1)
        if c == b"\x00":
            break
        else:
            s = s + c
    f.seek(pos)
    return s.decode(encoding)


def get_blob_at(f, addr: int, size: int) -> bytes:
    pos = f.tell()
    f.seek(addr)
    c = f.read(size)
    f.seek(pos)
    return c


@dataclass
class ArcEntry:
    name: str
    data: bytes
    hash: int


def read_arc(path: Path) -> tuple[int, List[ArcEntry]]:
    with path.open("rb") as f:
        assert f.read(8) == b"EZBIND\x00\x00", "Not an EZBIND file!"
        file_count, alignment = struct.unpack("<II", f.read(8))
        headers = []
        for _ in range(file_count):
            name_offset, file_size, file_pos, hash_val = struct.unpack("<IIII", f.read(0x10))
            headers.append((name_offset, file_size, file_pos, hash_val))

        entries: List[ArcEntry] = []
        for name_offset, file_size, file_pos, hash_val in headers:
            name = get_string_at(f, name_offset)
            data = get_blob_at(f, file_pos, file_size)
            entries.append(ArcEntry(name, data, hash_val))

    return alignment, entries


def write_arc(path: Path, alignment: int, entries: List[ArcEntry]) -> None:
    def align(n: int, a: int) -> int:
        return (n + (a - 1)) & ~(a - 1) if a > 0 else n

    out = BytesIO()
    out.write(b"EZBIND\x00\x00")
    out.write(struct.pack("<II", len(entries), alignment))

    table_pos = out.tell()
    out.write(b"\x00" * (len(entries) * 0x10))

    name_offsets = []
    for e in entries:
        name_offsets.append(out.tell())
        out.write(e.name.encode("ascii") + b"\x00")

    data_start = align(out.tell(), alignment)
    out.seek(data_start)

    file_positions = []
    file_sizes = []
    for e in entries:
        pos = align(out.tell(), alignment)
        if pos != out.tell():
            out.write(b"\x00" * (pos - out.tell()))
        file_positions.append(out.tell())
        out.write(e.data)
        file_sizes.append(len(e.data))

    out.seek(table_pos)
    for i, e in enumerate(entries):
        out.write(struct.pack("<IIII", name_offsets[i], file_sizes[i], file_positions[i], e.hash))

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(out.getvalue())


def apply_translations_to_scr(scr_gz: bytes, xml_path: Path) -> bytes:
    raw = gzip.decompress(scr_gz)
    scr = BytesIO(raw)
    assert scr.read(8) == b"FaceChat", "Not a FaceChat file!"
    unk8, str_count, code_count, unk_last = struct.unpack("<hhhH", scr.read(0x8))
    code_section = scr.read(code_count * 2)
    len_off = 0x10 + code_count * 2
    str_off = 0x10 + (code_count * 2) + (str_count * 2)

    scr.seek(len_off)
    offsets = struct.unpack(f"<{str_count}H", scr.read(str_count * 2))
    original_strings = []
    for s in offsets:
        original_strings.append(get_string_at(scr, str_off + s, "euc-jp"))

    translations = {}
    if xml_path.exists():
        xml_tree = ET.parse(str(xml_path))
        for entry in xml_tree.findall(".//Entry"):
            id_text = entry.findtext("Id")
            en_text = entry.findtext("EnglishText")
            if id_text is None:
                continue
            try:
                idx = int(id_text)
            except ValueError:
                continue
            if en_text is not None and en_text.strip() != "":
                translations[idx] = en_text.replace("\r\n", "\n")

    new_strings = []
    for i in range(str_count):
        new_strings.append(translations.get(i, original_strings[i]))

    string_blob = BytesIO()
    new_offsets = []
    for s in new_strings:
        new_offsets.append(string_blob.tell())
        string_blob.write(s.encode("euc-jp", errors="replace") + b"\x00")

    # Guard: FaceChat stores 16-bit offsets to strings; refuse if overflow
    if any(off > 0xFFFF for off in new_offsets) or string_blob.tell() > 0xFFFF:
        raise ValueError(f"String table too large for 16-bit offsets in {xml_path.name} (size={string_blob.tell()} bytes)")

    out = BytesIO()
    out.write(b"FaceChat")
    out.write(struct.pack("<hhhH", unk8, str_count, code_count, unk_last))
    out.write(code_section)
    out.write(struct.pack(f"<{str_count}H", *new_offsets))
    out.write(string_blob.getvalue())

    return gzip.compress(out.getvalue())


def apply_folder(subdir: str, disc_root: Path, xml_root: Path, out_root: Path, only_arcs: list[str] | None = None, pad_to_original_size: bool = False) -> None:
    in_dir = disc_root / "USRDIR" / subdir
    out_dir = out_root / "USRDIR" / subdir
    xml_dir = xml_root / subdir

    normalized_only: set[str] | None = None
    if only_arcs:
        normalized_only = set()
        for nm in only_arcs:
            normalized_only.add(nm if nm.lower().endswith(".arc") else f"{nm}.arc")

    for arc_path in in_dir.glob("*.arc"):
        if normalized_only is not None and arc_path.name not in normalized_only:
            continue
        alignment, entries = read_arc(arc_path)
        new_entries: List[ArcEntry] = []
        for e in entries:
            if e.name.lower().endswith(".scr"):
                xml_path = xml_dir / Path(e.name).with_suffix(".xml").name
                if xml_path.exists():
                    try:
                        new_data = apply_translations_to_scr(e.data, xml_path)
                        new_entries.append(ArcEntry(e.name, new_data, e.hash))
                    except Exception:
                        new_entries.append(e)
                else:
                    new_entries.append(e)
            else:
                new_entries.append(e)
        target_path = out_dir / arc_path.name
        write_arc(target_path, alignment, new_entries)

        if pad_to_original_size:
            try:
                orig_size = arc_path.stat().st_size
                new_size = target_path.stat().st_size
                if new_size < orig_size:
                    # pad with zeros to keep exact byte size
                    with target_path.open("ab") as wf:
                        wf.write(b"\x00" * (orig_size - new_size))
                # if new_size > orig_size we leave as-is; order+filelist import will handle LBAs
            except Exception:
                pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply translated XML into .arc archives for Radiant Mythology 2")
    parser.add_argument("--target", choices=["facechat", "npc", "both"], default="facechat", help="Which subfolder to apply")
    parser.add_argument("--disc", default="0_disc", help="Path to disc root containing USRDIR")
    parser.add_argument("--xml", default="2_translated", help="Path to translated XML root")
    parser.add_argument("--out", default="3_patched", help="Path to output root")
    parser.add_argument("--only", action="append", help="Only process the given .arc name(s) (e.g., ev0000 or ev0000.arc). Can be specified multiple times.")
    parser.add_argument("--pad-size", action="store_true", help="Pad rebuilt .arc to original size if smaller to minimize LBA shifts.")
    args = parser.parse_args()

    disc_root = Path(args.disc)
    xml_root = Path(args.xml)
    out_root = Path(args.out)

    if args.target in ("facechat", "both"):
        apply_folder("facechat", disc_root, xml_root, out_root, args.only, args.pad_size)
    if args.target in ("npc", "both"):
        apply_folder("npc", disc_root, xml_root, out_root, args.only, args.pad_size)


if __name__ == "__main__":
    main()


