#!/usr/bin/env python3
"""
QUEST-APPLY - Standalone script
Rebuild qtext.arc from a modified 0000.bin file
"""

from dataclasses import dataclass
from pathlib import Path
from io import BytesIO
from typing import List
import struct
import argparse
import gzip
import sys
import subprocess
from lxml import etree as ET


@dataclass
class ArcEntry:
    name: str
    data: bytes
    hash: int


def get_string_at(f, addr: int, encoding: str = "euc-jp") -> str:
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


def write_arc(path: Path, alignment: int, entries: List[ArcEntry], target_size: int = None) -> None:
    """Write ARC file, optionally padding to target_size to maintain ISO compatibility
    Padding is added AFTER the file data to preserve file structure integrity"""
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
        file_sizes.append(len(e.data))  # Use actual data size

    out.seek(table_pos)
    for i, e in enumerate(entries):
        out.write(struct.pack("<IIII", name_offsets[i], file_sizes[i], file_positions[i], e.hash))

    # Get the current size
    arc_data = out.getvalue()
    current_size = len(arc_data)
    
    # If target_size is specified and current size is smaller, pad AFTER file data
    # This preserves the file structure - padding goes at the end of the ARC file
    if target_size is not None and current_size < target_size:
        padding_needed = target_size - current_size
        # Pad at the end of the file (after all file data)
        arc_data += b"\x00" * padding_needed
        print(f"  Padded ARC file to match original size: {target_size} bytes (+{padding_needed} bytes)")
        print(f"  Note: Padding added at end of file to preserve file structure")
    elif target_size is not None and current_size > target_size:
        print(f"  WARNING: New ARC file is larger than original ({current_size} > {target_size} bytes)")
        print(f"  This may cause ISO corruption. Consider shortening translations.")
        # Still write it, but warn the user
    elif target_size is not None and current_size == target_size:
        print(f"  ARC file size matches original: {target_size} bytes")

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(arc_data)


# XML-related functions for applying translations
def is_valid_japanese_text(text: str) -> bool:
    """Check if a string is valid Japanese text worth keeping (same as quest_extract.py)"""
    if not text or len(text.strip()) == 0:
        return False
    
    # Filter out very short strings (likely control codes)
    if len(text.strip()) < 3:
        return False
    
    # Must contain at least one Japanese character (Hiragana, Katakana, or Kanji)
    has_japanese = any(
        0x3040 <= ord(c) <= 0x309F or  # Hiragana
        0x30A0 <= ord(c) <= 0x30FF or  # Katakana
        0x4E00 <= ord(c) <= 0x9FAF or  # Kanji
        0xFF00 <= ord(c) <= 0xFFEF     # Full-width
        for c in text
    )
    
    if not has_japanese:
        return False
    
    # Filter out strings that are mostly control characters or symbols
    printable_count = sum(1 for c in text if c.isprintable() or ord(c) > 127)
    if printable_count < len(text) * 0.5:  # At least 50% should be printable
        return False
    
    return True


def extract_strings_from_bin(bin_data: bytes) -> List[tuple[int, str]]:
    """Extract all Japanese strings from a .bin file, returning (position, string) tuples
    Uses the same filtering logic as quest_extract.py to ensure ID matching
    Handles gzip-compressed files automatically"""
    import gzip
    
    # Check if file is gzip-compressed (starts with 1f 8b)
    original_size = len(bin_data)
    if len(bin_data) >= 2 and bin_data[0] == 0x1f and bin_data[1] == 0x8b:
        try:
            # Decompress gzip data
            bin_data = gzip.decompress(bin_data)
            print(f"    Decompressed gzip data: {original_size} -> {len(bin_data)} bytes")
        except Exception as e:
            print(f"    Warning: Failed to decompress gzip data: {e}")
            return []
    
    strings = []
    total_strings_found = 0
    
    # Scan the entire file for null-terminated strings (same method as quest_extract.py)
    pos = 0
    current_string = b""
    string_start = 0
    
    while pos < len(bin_data):
        byte = bin_data[pos]
        
        if byte == 0:
            # End of string
            if len(current_string) > 0:
                total_strings_found += 1
                try:
                    decoded = current_string.decode("euc-jp")
                    # Only add if it's valid Japanese text (same filter as extract)
                    if is_valid_japanese_text(decoded):
                        strings.append((string_start, decoded.strip()))
                except UnicodeDecodeError:
                    # Not a valid string, skip
                    pass
            current_string = b""
            string_start = pos + 1
        else:
            # Add byte to current string
            if len(current_string) == 0:
                string_start = pos
            current_string += bytes([byte])
        
        pos += 1
    
    # Handle last string if file doesn't end with null
    if len(current_string) > 0:
        total_strings_found += 1
        try:
            decoded = current_string.decode("euc-jp")
            if is_valid_japanese_text(decoded):
                strings.append((string_start, decoded.strip()))
        except UnicodeDecodeError:
            pass
    
    print(f"    Found {total_strings_found} total strings, {len(strings)} valid Japanese strings")
    
    # Remove duplicates while preserving order (same as extract)
    seen = set()
    unique_strings = []
    for pos, s in strings:
        normalized = s.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique_strings.append((pos, normalized))
    
    if len(unique_strings) != len(strings):
        print(f"    Removed {len(strings) - len(unique_strings)} duplicate strings")
    
    return unique_strings


def apply_translations_to_bin(bin_data: bytes, xml_path: Path, reference_bin_data: bytes = None) -> bytes:
    """Apply translations to a .bin file containing EUC-JP encoded strings.
    Uses exact same extraction logic as quest_extract.py to ensure ID matching.
    Handles gzip compression automatically.
    
    Args:
        bin_data: The binary data to modify (gzip-compressed, will be decompressed/modified/recompressed)
        xml_path: Path to XML file with translations
        reference_bin_data: Reference binary for string extraction (if different from bin_data)
    """
    import gzip
    
    # Check if bin_data is gzip-compressed
    is_compressed = len(bin_data) >= 2 and bin_data[0] == 0x1f and bin_data[1] == 0x8b
    original_compressed_data = bin_data
    original_compressed_size = len(bin_data)
    
    # Decompress if needed
    if is_compressed:
        try:
            bin_data = gzip.decompress(bin_data)
            print(f"    Decompressed for modification: {original_compressed_size} -> {len(bin_data)} bytes")
        except Exception as e:
            print(f"    ERROR: Failed to decompress: {e}")
            return original_compressed_data
    
    # Use reference data for string extraction if provided (for better string matching)
    # But always apply to bin_data (which must be the ARC data for size preservation)
    extraction_data = reference_bin_data if reference_bin_data is not None else bin_data
    
    # Decompress reference data if needed
    if extraction_data != bin_data and len(extraction_data) >= 2 and extraction_data[0] == 0x1f and extraction_data[1] == 0x8b:
        try:
            extraction_data = gzip.decompress(extraction_data)
        except:
            pass
    
    # Extract original strings with their positions (same method as extract)
    # Note: extract_strings_from_bin will handle decompression internally
    string_positions = extract_strings_from_bin(extraction_data)
    
    if len(string_positions) == 0:
        print("    Warning: No strings found in .bin file")
        # Return original compressed data if it was compressed
        if is_compressed:
            return original_compressed_data
        return bytes(bin_data)
    
    print(f"    Found {len(string_positions)} strings in binary file")
    
    # Load translations from XML
    translations = {}
    if xml_path.exists():
        xml_tree = ET.parse(str(xml_path))
        for entry in xml_tree.findall(".//Entry"):
            id_text = entry.findtext("Id")
            if id_text is None:
                continue
            try:
                idx = int(id_text)
            except ValueError:
                continue
            
            # Handle self-closing tags: <EnglishText/> vs <EnglishText>text</EnglishText>
            en_elem = entry.find("EnglishText")
            if en_elem is not None:
                en_text = en_elem.text if en_elem.text else ""
                if en_text.strip() != "":
                    translations[idx] = en_text.replace("\r\n", "\n")
    
    if len(translations) == 0:
        print("    No translations found in XML")
        # Return original compressed data if it was compressed
        if is_compressed:
            return original_compressed_data
        return bytes(bin_data)
    
    print(f"    Found {len(translations)} translations to apply")
    
    # Verify we have the same number of strings as XML entries
    if len(string_positions) != len(translations) and len(translations) > 0:
        print(f"    WARNING: String count mismatch - Binary has {len(string_positions)} strings, XML has translations for {len(translations)} entries")
        print(f"    This may cause incorrect translations. Make sure extraction and application use the same logic.")
    
    # Build new binary data - start with exact copy
    new_data = bytearray(bin_data)
    
    # Apply translations by index (matching XML ID to extraction order)
    applied_count = 0
    for idx, (pos, original_string) in enumerate(string_positions):
        if idx in translations:
            translated = translations[idx]
            # Encode original string to get exact byte representation
            original_bytes = original_string.encode("euc-jp") + b"\x00"
            # Encode translated string
            translated_bytes = translated.encode("euc-jp", errors="replace") + b"\x00"
            
            # CRITICAL: Verify the original string matches what's actually at this position in bin_data
            # Note: pos is relative to extraction_data, but we need to check bin_data
            # If extraction_data != bin_data, we need to find the string in bin_data
            actual_bytes_at_pos = bin_data[pos:pos+len(original_bytes)] if pos < len(bin_data) else b""
            
            # If sizes match, positions should match too
            if len(bin_data) == len(extraction_data):
                if actual_bytes_at_pos != original_bytes:
                    print(f"    WARNING: String at position {pos} doesn't match expected bytes")
                    print(f"      Expected: {original_bytes[:50]}...")
                    print(f"      Actual:   {actual_bytes_at_pos[:50]}...")
                    # Try to find the string elsewhere in bin_data
                    search_bytes = original_string.encode("euc-jp")
                    found_pos = bin_data.find(search_bytes)
                    if found_pos != -1:
                        print(f"      Found string at different position: {found_pos}")
                        pos = found_pos  # Update position
                    else:
                        print(f"      String not found in bin_data - skipping")
                        continue
            else:
                # Sizes don't match - find string in bin_data
                search_bytes = original_string.encode("euc-jp")
                found_pos = bin_data.find(search_bytes)
                if found_pos != -1:
                    pos = found_pos  # Use found position
                else:
                    print(f"    WARNING: String not found in bin_data (size mismatch) - skipping")
                    continue
            
            # Check if translated string fits in the same space
            if len(translated_bytes) <= len(original_bytes):
                # Replace in place - this preserves file size
                for i, byte in enumerate(translated_bytes):
                    if pos + i < len(new_data):
                        new_data[pos + i] = byte
                # Zero out remaining bytes if translated is shorter
                for i in range(len(translated_bytes), len(original_bytes)):
                    if pos + i < len(new_data):
                        new_data[pos + i] = 0
                applied_count += 1
            else:
                # Translated string is longer - this is a problem
                print(f"    ERROR: Translation for string {idx} is too long")
                print(f"      Original: {len(original_bytes)} bytes")
                print(f"      Translated: {len(translated_bytes)} bytes")
                print(f"      Original text: {original_string[:50]}...")
                print(f"      Translated text: {translated[:50]}...")
                raise ValueError(
                    f"Translation for string {idx} is too long "
                    f"(original: {len(original_bytes)}, translated: {len(translated_bytes)})"
                )
    
    print(f"    Applied {applied_count} translations")
    
    # Verify decompressed size hasn't changed
    if len(new_data) != len(bin_data):
        raise ValueError(f"Decompressed binary size changed from {len(bin_data)} to {len(new_data)} bytes - this should never happen!")
    
    # Recompress if original was compressed
    if is_compressed:
        try:
            # Extract original mtime from gzip header
            original_mtime = None
            if len(original_compressed_data) >= 10:
                try:
                    original_mtime = struct.unpack("<I", original_compressed_data[4:8])[0]
                except Exception:
                    pass
            
            # Compress the modified data with original mtime preserved
            gzip_buffer = BytesIO()
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
            
            gz_file.write(bytes(new_data))
            gz_file.close()
            compressed_data = gzip_buffer.getvalue()
            print(f"    Recompressed: {len(new_data)} -> {len(compressed_data)} bytes")
            
            # CRITICAL: If sizes don't match exactly, we have a problem
            # Gzip padding corrupts the stream, so we can't pad
            if len(compressed_data) > original_compressed_size:
                print(f"    ERROR: Compressed size ({len(compressed_data)}) > original ({original_compressed_size})")
                print(f"    Translations are too long! Cannot fit in original space.")
                print(f"    This will cause ISO corruption. Please shorten translations.")
                raise ValueError(f"Compressed size too large: {len(compressed_data)} > {original_compressed_size}")
            elif len(compressed_data) < original_compressed_size:
                # We can't pad gzip data (it corrupts the stream)
                # Instead, we need to ensure translations are short enough
                print(f"    WARNING: Compressed size ({len(compressed_data)}) < original ({original_compressed_size})")
                print(f"    Size difference: {original_compressed_size - len(compressed_data)} bytes")
                print(f"    Note: Cannot pad gzip data without corrupting it.")
                print(f"    The file will be smaller, which may cause LBA shifts in ISO.")
                # Return the smaller compressed data - ISO replacement tool should handle it
                # But warn that this might cause issues
            
            return compressed_data
        except Exception as e:
            print(f"    ERROR: Failed to recompress: {e}")
            return original_compressed_data
    
    return bytes(new_data)


def prepare_bin_for_arc(modified_bin_data: bytes, original_arc_entry_data: bytes) -> bytes:
    """Prepare modified .bin file for ARC insertion.
    Handles gzip compression automatically based on original ARC entry.
    Preserves original compression parameters (mtime, etc.) when possible.
    Assumes modified_bin_data is decompressed (user edits the decompressed version).
    
    Args:
        modified_bin_data: The modified .bin file data (should be decompressed)
        original_arc_entry_data: The original data from ARC entry (to check compression)
    
    Returns:
        Prepared binary data ready for ARC insertion (compressed if original was compressed)
    """
    # Check if original ARC entry was gzip-compressed
    is_compressed = len(original_arc_entry_data) >= 2 and original_arc_entry_data[0] == 0x1f and original_arc_entry_data[1] == 0x8b
    
    # Extract original mtime from gzip header if compressed
    original_mtime = None
    if is_compressed and len(original_arc_entry_data) >= 10:
        try:
            import struct
            # Gzip header: 2 bytes magic, 1 byte method, 1 byte flags, 4 bytes mtime
            original_mtime = struct.unpack("<I", original_arc_entry_data[4:8])[0]
        except Exception:
            pass
    
    # Check if modified data is already compressed (user might have provided compressed version)
    modified_is_compressed = len(modified_bin_data) >= 2 and modified_bin_data[0] == 0x1f and modified_bin_data[1] == 0x8b
    
    if modified_is_compressed:
        # User provided compressed data - decompress first
        try:
            modified_bin_data = gzip.decompress(modified_bin_data)
            print(f"    Decompressed user-provided .bin file for processing")
        except Exception as e:
            print(f"    WARNING: Failed to decompress user-provided .bin: {e}")
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
                print(f"    Using original mtime: {original_mtime}")
            else:
                gz_file = gzip.GzipFile(
                    fileobj=gzip_buffer,
                    mode='wb',
                    compresslevel=9
                )
            
            gz_file.write(modified_bin_data)
            gz_file.close()
            compressed_data = gzip_buffer.getvalue()
            
            print(f"    Compressed modified .bin: {len(modified_bin_data)} -> {len(compressed_data)} bytes")
            
            # Verify the compressed data can be decompressed back to the same modified data
            try:
                verify_decompressed = gzip.decompress(compressed_data)
                if verify_decompressed == modified_bin_data:
                    print(f"    Verified: Compressed data decompresses correctly to modified file")
                else:
                    print(f"    WARNING: Compressed data verification failed - decompressed data doesn't match!")
                    diff_count = sum(1 for a, b in zip(verify_decompressed, modified_bin_data) if a != b)
                    print(f"      Mismatch at {diff_count} byte positions")
            except Exception as e:
                print(f"    WARNING: Could not verify compressed data: {e}")
            
            # Check size constraints
            original_compressed_size = len(original_arc_entry_data)
            if len(compressed_data) > original_compressed_size:
                print(f"    WARNING: Compressed size ({len(compressed_data)}) > original ({original_compressed_size})")
                print(f"    Size difference: {len(compressed_data) - original_compressed_size} bytes")
                print(f"    This may cause issues. Consider reducing the size of modifications.")
            elif len(compressed_data) < original_compressed_size:
                size_diff = original_compressed_size - len(compressed_data)
                print(f"    Note: Compressed size decreased by {size_diff} bytes (this is OK)")
                print(f"    ARC file will be padded to maintain ISO compatibility")
            
            return compressed_data
        except Exception as e:
            print(f"    ERROR: Failed to compress: {e}")
            import traceback
            traceback.print_exc()
            # Return original if compression fails
            return original_arc_entry_data
    else:
        # Original was not compressed - use modified data as-is
        print(f"    Using modified .bin as-is (original was not compressed)")
        return modified_bin_data


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


def replace_quest_files_in_iso(iso_path: Path, quest_folder: Path, umd_script: Path) -> bool:
    """Replace all quest files in ISO (excluding client folder and qtext.arc)"""
    if not quest_folder.exists():
        print(f"ERROR: Quest folder not found: {quest_folder}")
        return False
    
    if not quest_folder.is_dir():
        print(f"ERROR: Quest path is not a directory: {quest_folder}")
        return False
    
    print(f"\nReplacing other quest files in ISO...")
    print(f"  Quest folder: {quest_folder}")
    
    # Find all files to replace (excluding client folder and qtext.arc files)
    files_to_replace = []
    client_folder = quest_folder / "client"
    for file_path in quest_folder.rglob("*"):
        if file_path.is_file():
            # Skip files inside the client folder
            try:
                file_path.relative_to(client_folder)
                # If we can get relative path, it's inside client folder - skip it
                continue
            except ValueError:
                # Not inside client folder - check if it's qtext.arc
                if file_path.name.lower() == "qtext.arc":
                    # Skip qtext.arc - it's already handled above
                    continue
                # Include other files
                files_to_replace.append(file_path)
    
    if not files_to_replace:
        print(f"  No other quest files found to replace")
        return True
    
    print(f"  Found {len(files_to_replace)} file(s) to replace:")
    print()
    
    # Process each file
    success_count = 0
    failed_count = 0
    
    for i, file_path in enumerate(files_to_replace, 1):
        # Get relative path from quest folder
        relative_path = file_path.relative_to(quest_folder)
        
        # Convert to ISO path format
        iso_file_path = f"PSP_GAME/USRDIR/quest/{str(relative_path).replace(chr(92), '/')}"
        
        print(f"  [{i}/{len(files_to_replace)}] {relative_path}")
        
        success = replace_file_in_iso(iso_path, iso_file_path, file_path, umd_script)
        
        if success:
            success_count += 1
        else:
            failed_count += 1
            print(f"    WARNING: Failed to replace {iso_file_path}")
    
    # Summary
    if failed_count > 0:
        print(f"\n  Summary: {success_count} succeeded, {failed_count} failed")
        if failed_count > 0:
            print(f"  WARNING: {failed_count} file(s) failed to replace")
            return False
    else:
        print(f"\n  OK All quest files replaced successfully!")
    
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild qtext.arc from a modified 0000.bin file and replace in ISO")
    parser.add_argument("--arc", default="0_disc/PSP_GAME/USRDIR/quest/qtext.arc", 
                       help="Path to original qtext.arc file (default: 0_disc/PSP_GAME/USRDIR/quest/qtext.arc)")
    parser.add_argument("--bin", default="1_extracted/quest/qtext/0000.bin", 
                       help="Path to modified 0000.bin file (default: 1_extracted/quest/qtext/0000.bin)")
    parser.add_argument("--xml", 
                       help="Path to XML translation file (alternative to --bin, applies translations from XML)")
    parser.add_argument("--out", default="3_patched/PSP_GAME/USRDIR/quest/qtext.arc", 
                       help="Path to output patched ARC file (default: 3_patched/PSP_GAME/USRDIR/quest/qtext.arc)")
    parser.add_argument("--iso", default="build/RM2_translated.iso", 
                       help="Path to ISO file to update (default: build/RM2_translated.iso)")
    parser.add_argument("--quest-folder", default="0_disc/PSP_GAME/USRDIR/quest", 
                       help="Path to quest folder for replacing other files (default: 0_disc/PSP_GAME/USRDIR/quest)")
    parser.add_argument("--no-iso", action="store_true", 
                       help="Skip ISO replacement (only rebuild ARC file)")
    args = parser.parse_args()

    arc_path = Path(args.arc)
    bin_path = Path(args.bin) if args.bin else None
    xml_path = Path(args.xml) if args.xml else None
    out_path = Path(args.out)
    iso_path = Path(args.iso) if not args.no_iso else None
    quest_folder = Path(args.quest_folder) if not args.no_iso else None
    
    if not arc_path.exists():
        print(f"ERROR: ARC file not found: {arc_path}")
        return
    
    # Must provide either --bin or --xml
    if not xml_path and not bin_path:
        print(f"ERROR: Must provide either --bin or --xml")
        return
    
    if xml_path and not xml_path.exists():
        print(f"ERROR: XML file not found: {xml_path}")
        return
    
    if bin_path and not bin_path.exists():
        print(f"ERROR: Modified .bin file not found: {bin_path}")
        return
    
    # Get original ARC file size BEFORE processing (critical for ISO compatibility)
    original_arc_size = arc_path.stat().st_size
    
    if xml_path:
        print(f"Rebuilding {arc_path.name} from XML translations...")
        print(f"  Original ARC size: {original_arc_size} bytes")
        print(f"  XML file: {xml_path}")
        print(f"  Output: {out_path}")
    else:
        print(f"Rebuilding {arc_path.name} from modified .bin file...")
        print(f"  Original ARC size: {original_arc_size} bytes")
        print(f"  Modified .bin: {bin_path}")
        print(f"  Output: {out_path}")
    
    try:
        # Read original ARC structure
        alignment, entries = read_arc(arc_path)
        
        # Process entries - replace .bin files with modified version
        new_entries: List[ArcEntry] = []
        replaced_count = 0
        
        for e in entries:
            if e.name.lower().endswith(".bin"):
                print(f"  Processing {e.name}...")
                print(f"    Original ARC entry size: {len(e.data)} bytes")
                
                if xml_path:
                    # Apply translations from XML to the original ARC entry data
                    print(f"    Applying translations from XML...")
                    modified_bin_data = apply_translations_to_bin(e.data, xml_path, reference_bin_data=e.data)
                    # prepare_bin_for_arc expects decompressed data, but apply_translations_to_bin
                    # returns compressed data if original was compressed, so we can use it directly
                    new_data = modified_bin_data
                else:
                    # Read modified .bin file
                    with bin_path.open("rb") as f:
                        modified_bin_data = f.read()
                    print(f"    Modified .bin size: {len(modified_bin_data)} bytes")
                    print(f"    First 16 bytes (hex): {' '.join(f'{b:02x}' for b in modified_bin_data[:16])}")
                    
                    # Compare with original decompressed data for verification
                    original_decompressed = e.data
                    if len(original_decompressed) >= 2 and original_decompressed[0] == 0x1f and original_decompressed[1] == 0x8b:
                        try:
                            original_decompressed = gzip.decompress(original_decompressed)
                            print(f"    Original decompressed size: {len(original_decompressed)} bytes")
                        except:
                            pass
                    
                    if len(modified_bin_data) == len(original_decompressed):
                        # Check if file actually changed
                        if modified_bin_data == original_decompressed:
                            print(f"    WARNING: Modified file appears identical to original!")
                        else:
                            diff_count = sum(1 for a, b in zip(modified_bin_data, original_decompressed) if a != b)
                            print(f"    File differs from original at {diff_count} byte positions")
                            # Show first few differences
                            diff_positions = [i for i, (a, b) in enumerate(zip(modified_bin_data, original_decompressed)) if a != b][:5]
                            for pos in diff_positions:
                                print(f"      Offset {pos:06x}: original={original_decompressed[pos]:02x} modified={modified_bin_data[pos]:02x}")
                    else:
                        print(f"    WARNING: Size mismatch! Modified={len(modified_bin_data)} bytes, Original={len(original_decompressed)} bytes")
                    
                    # Prepare the modified bin data (compress if original was compressed)
                    new_data = prepare_bin_for_arc(modified_bin_data, e.data)
                
                # Create new entry with modified data
                new_entries.append(ArcEntry(e.name, new_data, e.hash))
                replaced_count += 1
                print(f"    OK Replaced with modified .bin ({len(new_data)} bytes)")
            else:
                # Keep other entries as-is
                new_entries.append(e)
        
        if replaced_count == 0:
            print("  WARNING: No .bin files found in ARC to replace")
        
        # Write new ARC file with target size to maintain ISO compatibility
        write_arc(out_path, alignment, new_entries, target_size=original_arc_size)
        print(f"\nOK Created patched ARC: {out_path}")
        
        # Verify final size matches
        final_size = out_path.stat().st_size
        if final_size != original_arc_size:
            print(f"  WARNING: Final size ({final_size}) does not match original ({original_arc_size})")
        else:
            print(f"  OK Size verified: {final_size} bytes (matches original)")
        
        # Replace in ISO if requested
        if iso_path and not args.no_iso:
            script_dir = Path(__file__).parent
            umd_script = script_dir / "UMD-replace" / "umd_replace.py"
            
            print(f"\nReplacing quest files in ISO...")
            print(f"  ISO: {iso_path}")
            
            # First, replace qtext.arc
            print(f"\n[1/2] Replacing qtext.arc...")
            iso_file_path = "PSP_GAME/USRDIR/quest/qtext.arc"
            success = replace_file_in_iso(iso_path, iso_file_path, out_path, umd_script)
            
            if not success:
                print(f"\nERROR Failed to replace qtext.arc in ISO")
                sys.exit(1)
            
            print(f"  OK qtext.arc replaced successfully!")
            
            # Then, replace all other quest files (excluding client folder and qtext.arc)
            if quest_folder:
                print(f"\n[2/2] Replacing other quest files...")
                success = replace_quest_files_in_iso(iso_path, quest_folder, umd_script)
                
                if not success:
                    print(f"\nWARNING Some quest files failed to replace")
                    # Don't exit - qtext.arc was successful, which is the main goal
            
            print(f"\nOK Successfully replaced all quest files in ISO!")
    
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

