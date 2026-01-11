#!/usr/bin/env python3
"""
DUNGEON-APPLY - Rebuild dungeon ARC files from extracted/modified files
Similar to how facechat ARC files are rebuilt, but handles dungeon files
"""

from dataclasses import dataclass
from pathlib import Path
from io import BytesIO
from typing import List, Optional
import struct
import gzip
import argparse
import sys
import subprocess


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


def write_arc(path: Path, alignment: int, entries: List[ArcEntry], target_size: Optional[int] = None) -> None:
    """Write ARC file, optionally padding to target_size to maintain ISO compatibility"""
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

    # Get the current size
    arc_data = out.getvalue()
    current_size = len(arc_data)
    
    # If target_size is specified and current size is smaller, pad AFTER file data
    if target_size is not None and current_size < target_size:
        padding_needed = target_size - current_size
        arc_data += b"\x00" * padding_needed
        print(f"  Padded ARC file to match original size: {target_size} bytes (+{padding_needed} bytes)")
    elif target_size is not None and current_size > target_size:
        print(f"  WARNING: New ARC file is larger than original ({current_size} > {target_size} bytes)")
        print(f"  This may cause ISO corruption.")
    elif target_size is not None and current_size == target_size:
        print(f"  ARC file size matches original: {target_size} bytes")

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(arc_data)


def prepare_file_for_arc(modified_data: bytes, original_entry_data: bytes) -> bytes:
    """Prepare modified file data for ARC insertion.
    Handles gzip compression automatically based on original ARC entry.
    Preserves original compression parameters (mtime, etc.) when possible.
    
    Args:
        modified_data: The modified file data (should be decompressed if original was compressed)
        original_entry_data: The original data from ARC entry (to check compression)
    
    Returns:
        Prepared binary data ready for ARC insertion (compressed if original was compressed)
    """
    # Check if original ARC entry was gzip-compressed
    is_compressed = len(original_entry_data) >= 2 and original_entry_data[0] == 0x1f and original_entry_data[1] == 0x8b
    
    # Extract original mtime from gzip header if compressed
    original_mtime = None
    if is_compressed and len(original_entry_data) >= 10:
        try:
            # Gzip header: 2 bytes magic, 1 byte method, 1 byte flags, 4 bytes mtime
            original_mtime = struct.unpack("<I", original_entry_data[4:8])[0]
        except Exception:
            pass
    
    # Check if modified data is already compressed (user might have provided compressed version)
    modified_is_compressed = len(modified_data) >= 2 and modified_data[0] == 0x1f and modified_data[1] == 0x8b
    
    if modified_is_compressed:
        # User provided compressed data - decompress first
        try:
            modified_data = gzip.decompress(modified_data)
            print(f"    Decompressed user-provided file for processing")
        except Exception as e:
            print(f"    WARNING: Failed to decompress user-provided file: {e}")
            print(f"    Assuming it's already decompressed")
    
    if is_compressed:
        # Original was compressed - compress the modified data with original parameters
        try:
            # Use BytesIO to create gzip with custom mtime
            gzip_buffer = BytesIO()
            
            # Create GzipFile with original mtime if available
            if original_mtime is not None:
                gz_file = gzip.GzipFile(
                    fileobj=gzip_buffer,
                    mode='wb',
                    compresslevel=9,
                    mtime=original_mtime
                )
            else:
                gz_file = gzip.GzipFile(
                    fileobj=gzip_buffer,
                    mode='wb',
                    compresslevel=9
                )
            
            gz_file.write(modified_data)
            gz_file.close()
            compressed_data = gzip_buffer.getvalue()
            
            print(f"    Compressed modified file: {len(modified_data)} -> {len(compressed_data)} bytes")
            
            # Check size constraints
            original_compressed_size = len(original_entry_data)
            if len(compressed_data) > original_compressed_size:
                print(f"    WARNING: Compressed size ({len(compressed_data)}) > original ({original_compressed_size})")
                print(f"    Size difference: {len(compressed_data) - original_compressed_size} bytes")
                print(f"    This may cause issues. Consider reducing the size of modifications.")
            elif len(compressed_data) < original_compressed_size:
                size_diff = original_compressed_size - len(compressed_data)
                print(f"    Note: Compressed size decreased by {size_diff} bytes (this is OK)")
            
            return compressed_data
        except Exception as e:
            print(f"    ERROR: Failed to compress: {e}")
            import traceback
            traceback.print_exc()
            # Return original if compression fails
            return original_entry_data
    else:
        # Original was not compressed - use modified data as-is
        print(f"    Using modified file as-is (original was not compressed)")
        return modified_data


def replace_file_in_iso(iso_path: Path, iso_file_path: str, local_file_path: Path, umd_script: Path = None) -> bool:
    """Replace a file in the ISO using umd_replace.py"""
    if umd_script is None:
        script_dir = Path(__file__).parent
        umd_script = script_dir / "UMD-replace" / "umd_replace.py"
    
    if not umd_script.exists():
        print(f"ERROR: UMD-replace script not found: {umd_script}")
        return False
    
    if not iso_path.exists():
        print(f"ERROR: ISO file not found: {iso_path}")
        return False
    
    if not local_file_path.exists():
        print(f"ERROR: File not found: {local_file_path}")
        return False
    
    print(f"  Replacing in ISO: {iso_file_path}")
    print(f"    Local file: {local_file_path}")
    
    try:
        cmd = [
            sys.executable,
            str(umd_script),
            str(iso_path),
            iso_file_path,
            str(local_file_path)
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        if result.stdout:
            print(f"    {result.stdout.strip()}")
        if result.stderr:
            print(f"    {result.stderr.strip()}", file=sys.stderr)
        
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"    FAILED")
        if e.stdout:
            print(f"    STDOUT: {e.stdout}")
        if e.stderr:
            print(f"    STDERR: {e.stderr}")
        print(f"    Exit code: {e.returncode}")
        return False
        
    except Exception as e:
        print(f"    ERROR: {e}")
        return False


def rebuild_arc(arc_path: Path, extracted_dir: Path, out_path: Path, pad_to_original: bool = False, iso_path: Optional[Path] = None) -> bool:
    """Rebuild an ARC file from extracted/modified files
    
    Args:
        arc_path: Path to original ARC file
        extracted_dir: Directory containing extracted/modified files
        out_path: Path to output rebuilt ARC file
        pad_to_original: If True, pad the ARC file to match original size
    
    Returns:
        True if successful, False otherwise
    """
    if not arc_path.exists():
        print(f"ERROR: ARC file not found: {arc_path}")
        return False
    
    if not extracted_dir.exists():
        print(f"ERROR: Extracted directory not found: {extracted_dir}")
        return False
    
    print(f"Rebuilding {arc_path.name}...")
    print(f"  Original ARC: {arc_path}")
    print(f"  Extracted files: {extracted_dir}")
    print(f"  Output: {out_path}")
    
    try:
        # Read original ARC structure
        alignment, entries = read_arc(arc_path)
        original_arc_size = arc_path.stat().st_size
        
        # Process entries - replace with modified files if they exist
        new_entries: List[ArcEntry] = []
        replaced_count = 0
        skipped_count = 0
        
        for e in entries:
            # Look for modified file in extracted directory
            modified_file = extracted_dir / e.name
            
            # Skip if it's a directory (shouldn't happen, but handle gracefully)
            if modified_file.is_dir():
                print(f"  Skipping {e.name} - is a directory, not a file")
                new_entries.append(e)
                skipped_count += 1
                continue
            
            if modified_file.exists():
                print(f"  Processing {e.name}...")
                print(f"    Original ARC entry size: {len(e.data)} bytes")
                
                # Read modified file with better error handling
                try:
                    with modified_file.open("rb") as f:
                        modified_data = f.read()
                    print(f"    Modified file size: {len(modified_data)} bytes")
                except PermissionError as pe:
                    print(f"    ERROR: Permission denied accessing {modified_file}")
                    print(f"    This file may be locked by another process (e.g., Windows Explorer)")
                    print(f"    Keeping original entry")
                    new_entries.append(e)
                    skipped_count += 1
                    continue
                except Exception as ex:
                    print(f"    ERROR: Failed to read {modified_file}: {ex}")
                    print(f"    Keeping original entry")
                    new_entries.append(e)
                    skipped_count += 1
                    continue
                
                # Prepare the modified file data (compress if original was compressed)
                new_data = prepare_file_for_arc(modified_data, e.data)
                
                # Create new entry with modified data
                new_entries.append(ArcEntry(e.name, new_data, e.hash))
                replaced_count += 1
                print(f"    OK Replaced with modified file ({len(new_data)} bytes)")
            else:
                # Keep original entry
                new_entries.append(e)
                skipped_count += 1
        
        print(f"\n  Summary: {replaced_count} file(s) replaced, {skipped_count} file(s) kept as original")
        
        # Write new ARC file
        target_size = original_arc_size if pad_to_original else None
        write_arc(out_path, alignment, new_entries, target_size=target_size)
        
        print(f"\nOK Created patched ARC: {out_path}")
        
        # Verify final size
        final_size = out_path.stat().st_size
        if pad_to_original and final_size != original_arc_size:
            print(f"  WARNING: Final size ({final_size}) does not match original ({original_arc_size})")
        elif pad_to_original:
            print(f"  OK Size verified: {final_size} bytes (matches original)")
        
        # Replace in ISO if requested
        if iso_path:
            script_dir = Path(__file__).parent
            umd_script = script_dir / "UMD-replace" / "umd_replace.py"
            
            # Determine ISO file path (preserve relative path structure)
            # Find PSP_GAME in the path and get everything after it
            arc_path_str = str(arc_path)
            psp_game_idx = arc_path_str.find("PSP_GAME")
            if psp_game_idx != -1:
                iso_file_path = arc_path_str[psp_game_idx:].replace("\\", "/")
            else:
                # Fallback: assume it's in PSP_GAME/USRDIR/dungeon/
                iso_file_path = f"PSP_GAME/USRDIR/dungeon/{arc_path.name}"
            
            print(f"\nReplacing ARC file in ISO...")
            print(f"  ISO: {iso_path}")
            print(f"  ISO path: {iso_file_path}")
            
            success = replace_file_in_iso(iso_path, iso_file_path, out_path, umd_script)
            
            if not success:
                print(f"\nERROR: Failed to replace {arc_path.name} in ISO")
                return False
            
            print(f"  OK {arc_path.name} replaced successfully in ISO!")
        
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild dungeon ARC files from extracted/modified files")
    parser.add_argument("--arc", required=True,
                       help="Path to original ARC file (e.g., 0_disc/PSP_GAME/USRDIR/dungeon/ship1.arc)")
    parser.add_argument("--extracted", required=True,
                       help="Path to directory containing extracted/modified files (e.g., 1_extracted/dungeon/qtext)")
    parser.add_argument("--out", 
                       help="Path to output patched ARC file (default: 3_patched/PSP_GAME/USRDIR/dungeon/<arc_name>)")
    parser.add_argument("--pad-size", action="store_true",
                       help="Pad rebuilt ARC to original size if smaller (to minimize LBA shifts)")
    parser.add_argument("--iso", 
                       help="Path to ISO file to update (e.g., build/RM2_translated.iso)")
    parser.add_argument("--no-iso", action="store_true",
                       help="Skip ISO replacement (only rebuild ARC file)")
    args = parser.parse_args()

    arc_path = Path(args.arc)
    extracted_dir = Path(args.extracted)
    
    # Determine output path
    if args.out:
        out_path = Path(args.out)
    else:
        # Default: 3_patched/PSP_GAME/USRDIR/dungeon/<arc_name>
        arc_name = arc_path.name
        # Try to preserve the relative path structure
        if "dungeon" in str(arc_path):
            out_path = Path("3_patched") / "PSP_GAME" / "USRDIR" / "dungeon" / arc_name
        else:
            # Fallback: just put in 3_patched with same name
            out_path = Path("3_patched") / arc_name
    
    # Determine expected extracted folder name (should match ARC filename without extension)
    arc_stem = arc_path.stem  # filename without .arc extension
    # Check if extracted_dir already contains the arc_stem subfolder
    if (extracted_dir / arc_stem).exists():
        # Use arc_stem subfolder (new structure)
        extracted_dir = extracted_dir / arc_stem
        print(f"  Using extracted files from: {extracted_dir}")
    elif extracted_dir.exists() and any(extracted_dir.iterdir()):
        # Use extracted_dir directly (old structure or flat)
        print(f"  Using extracted files from: {extracted_dir}")
    else:
        # Try to find the subfolder
        potential_subfolder = extracted_dir / arc_stem
        if potential_subfolder.exists():
            extracted_dir = potential_subfolder
            print(f"  Found extracted files in subfolder: {extracted_dir}")
    
    # Determine ISO path
    iso_path = None
    if not args.no_iso:
        if args.iso:
            iso_path = Path(args.iso)
        else:
            # Default ISO path
            iso_path = Path("build/RM2_translated.iso")
            if not iso_path.exists():
                print(f"WARNING: Default ISO file not found: {iso_path}")
                print(f"  Use --iso to specify ISO path or --no-iso to skip ISO replacement")
                iso_path = None
    
    success = rebuild_arc(arc_path, extracted_dir, out_path, pad_to_original=args.pad_size, iso_path=iso_path)
    
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
