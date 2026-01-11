#!/usr/bin/env python3
"""
EXTRACT-ARC - Extract files from any ARC archive
General-purpose ARC file extractor
"""

import argparse
from pathlib import Path
from dataclasses import dataclass
import struct
from typing import List
import gzip


@dataclass
class ArcEntry:
    name: str
    data: bytes
    hash: int


def get_string_at(f, addr: int, encoding: str = "ascii") -> str:
    pos = f.tell()
    f.seek(addr)
    s = b""
    while True:
        c = f.read(1)
        if c == b"\x00" or len(c) == 0:
            break
        else:
            s = s + c
    f.seek(pos)
    try:
        return s.decode(encoding)
    except UnicodeDecodeError:
        return ""


def get_blob_at(f, addr: int, size: int) -> bytes:
    pos = f.tell()
    f.seek(addr)
    c = f.read(size)
    f.seek(pos)
    return c


def read_arc(path: Path) -> tuple[int, List[ArcEntry]]:
    """Read an ARC file and return alignment and entries"""
    with path.open("rb") as f:
        assert f.read(8) == b"EZBIND\x00\x00", "Not an EZBIND file!"
        file_count, alignment = struct.unpack("<II", f.read(8))
        headers = []
        for _ in range(file_count):
            name_offset, file_size, file_pos, hash_val = struct.unpack("<IIII", f.read(0x10))
            headers.append((name_offset, file_size, file_pos, hash_val))

        entries: List[ArcEntry] = []
        for name_offset, file_size, file_pos, hash_val in headers:
            name = get_string_at(f, name_offset, "ascii")
            data = get_blob_at(f, file_pos, file_size)
            entries.append(ArcEntry(name, data, hash_val))

    return alignment, entries


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract files from any ARC archive")
    parser.add_argument("--arc", required=True, help="Path to ARC file")
    parser.add_argument("--out", help="Path to output directory (default: same directory as ARC)")
    args = parser.parse_args()

    arc_path = Path(args.arc).resolve()
    
    if not arc_path.exists():
        print(f"ERROR: ARC file not found: {arc_path}")
        return
    
    # Default output directory is same as ARC file location
    if args.out:
        out_dir = Path(args.out).resolve()
    else:
        out_dir = arc_path.parent / f"{arc_path.stem}_extracted"
    
    print(f"Extracting from {arc_path.name}...")
    print(f"  Output directory: {out_dir}")
    
    try:
        alignment, entries = read_arc(arc_path)
        print(f"  Found {len(entries)} file(s) in archive")
        
        # Extract each file
        for entry in entries:
            output_path = out_dir / entry.name
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if the data is gzip compressed (starts with 0x1f 0x8b)
            if len(entry.data) >= 2 and entry.data[0] == 0x1f and entry.data[1] == 0x8b:
                try:
                    decompressed_data = gzip.decompress(entry.data)
                    output_path.write_bytes(decompressed_data)
                    print(f"  Extracted (decompressed): {entry.name} ({len(entry.data)} bytes compressed -> {len(decompressed_data)} bytes decompressed) -> {output_path}")
                except Exception as e:
                    print(f"  WARNING: Failed to decompress {entry.name}: {e}. Writing raw data.")
                    output_path.write_bytes(entry.data)
                    print(f"  Extracted: {entry.name} ({len(entry.data)} bytes) -> {output_path}")
            else:
                output_path.write_bytes(entry.data)
                print(f"  Extracted: {entry.name} ({len(entry.data)} bytes) -> {output_path}")
        
        print(f"\nOK Extraction complete!")
        print(f"  Files extracted to: {out_dir}")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

