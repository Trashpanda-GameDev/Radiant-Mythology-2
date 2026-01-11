#!/usr/bin/env python3
"""
QUEST-EXTRACT-ARC - Extract files from qtext.arc archive
Extracts the 0000.bin file from the ARC archive to the 1_extracted folder structure
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
    parser = argparse.ArgumentParser(description="Extract files from ARC archive")
    parser.add_argument("--arc", default="0_disc/PSP_GAME/USRDIR/quest/qtext.arc", 
                       help="Path to ARC file")
    parser.add_argument("--out", default="1_extracted/quest", 
                       help="Path to output directory (will create subfolder based on ARC name)")
    parser.add_argument("--subfolder", 
                       help="Subfolder name (default: ARC filename without .arc extension, or 'qtext' for quest files)")
    args = parser.parse_args()

    arc_path = Path(args.arc).resolve()
    out_dir = Path(args.out).resolve()
    
    if not arc_path.exists():
        print(f"ERROR: ARC file not found: {arc_path}")
        return
    
    # Determine subfolder name
    if args.subfolder:
        subfolder_name = args.subfolder
    else:
        # Use ARC filename without extension, or "qtext" for quest files (backward compatibility)
        arc_name = arc_path.stem  # filename without .arc extension
        if "quest" in str(arc_path).lower() and arc_name == "qtext":
            subfolder_name = "qtext"  # Keep backward compatibility
        else:
            subfolder_name = arc_name  # Use ARC filename (e.g., "ship1", "01_coral_woods01")
    
    print(f"Extracting from {arc_path.name}...")
    print(f"  Output directory: {out_dir}")
    print(f"  Subfolder: {subfolder_name}")
    
    try:
        alignment, entries = read_arc(arc_path)
        print(f"  Found {len(entries)} file(s) in archive")
        
        # Extract each file
        for entry in entries:
            # Create output path: 1_extracted/<out_dir>/<subfolder_name>/<entry.name>
            output_path = out_dir / subfolder_name / entry.name
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if file is gzip-compressed and decompress if needed
            data = entry.data
            is_compressed = len(data) >= 2 and data[0] == 0x1f and data[1] == 0x8b
            
            if is_compressed:
                try:
                    decompressed_data = gzip.decompress(data)
                    data = decompressed_data
                    print(f"  Decompressed {entry.name}: {len(entry.data)} -> {len(data)} bytes")
                except Exception as e:
                    print(f"  Warning: Failed to decompress {entry.name}: {e}")
                    print(f"  Extracting as-is (compressed)")
            
            # Write file
            output_path.write_bytes(data)
            print(f"  Extracted: {entry.name} ({len(data)} bytes) -> {output_path}")
        
        print(f"\nOK Extraction complete!")
        print(f"  Files extracted to: {out_dir / subfolder_name}")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

