#!/usr/bin/env python3
"""
QUEST-EXTRACT - Standalone script
Extract quest text from qtext.arc/0000.bin and create XML translation templates
"""

from dataclasses import dataclass
from pathlib import Path
from io import BytesIO
from typing import List
import struct
import argparse
from lxml import etree as ET


@dataclass
class trEntry:
    jp_text: str
    en_text: str
    notes: str
    id: int
    status: str


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
            name = get_string_at(f, name_offset, "ascii")
            data = get_blob_at(f, file_pos, file_size)
            entries.append(ArcEntry(name, data, hash_val))

    return alignment, entries


def clean_xml_text(text: str) -> str:
    """Remove NULL bytes and control characters that aren't XML compatible"""
    if text is None:
        return ""
    # Remove NULL bytes and other control characters except newlines and tabs
    cleaned = "".join(char for char in text if ord(char) >= 32 or char in "\n\t\r")
    return cleaned


def makeNode(root: ET._Element, n: trEntry, id: int) -> ET._Element:
    entry = ET.SubElement(root, "Entry")
    ET.SubElement(entry, "PointerOffset")  # Empty PointerOffset to match format
    
    # JapaneseText - always has content
    jp_elem = ET.SubElement(entry, "JapaneseText")
    jp_elem.text = clean_xml_text(n.jp_text.replace("\r\n", "\n"))
    
    # EnglishText - self-closing if empty
    en_elem = ET.SubElement(entry, "EnglishText")
    en_text = clean_xml_text(n.en_text)
    if en_text:
        en_elem.text = en_text
    
    # Notes - self-closing if empty
    notes_elem = ET.SubElement(entry, "Notes")
    notes_text = clean_xml_text(n.notes)
    if notes_text:
        notes_elem.text = notes_text
    
    ET.SubElement(entry, "Id").text = str(id)
    ET.SubElement(entry, "Status").text = n.status
    return entry


def makeXml(entries: List[trEntry], friendly_name: str = None) -> bytes:
    root = ET.Element("SceneText")
    
    # Add Speakers section (empty, matching the format)
    speakers_node = ET.SubElement(root, "Speakers")
    ET.SubElement(speakers_node, "Section").text = "Speaker"
    
    # Add Strings section for quest dialogue
    text_node = ET.SubElement(root, "Strings")
    ET.SubElement(text_node, "Section").text = "Main Text"
    
    for n in entries:
        makeNode(text_node, n, n.id)
    
    # Add Unreferenced section (empty, matching the format)
    unreferenced_node = ET.SubElement(root, "Strings")
    ET.SubElement(unreferenced_node, "Section").text = "Unreferenced"
    
    # Create XML tree without declaration
    xml_bytes = ET.tostring(root, encoding="UTF-8", pretty_print=True, xml_declaration=False)
    return xml_bytes


def is_valid_japanese_text(text: str) -> bool:
    """Check if a string is valid Japanese text worth keeping"""
    if not text or len(text.strip()) == 0:
        return False
    
    # Filter out very short strings (likely control codes)
    if len(text.strip()) < 3:
        return False
    
    # Must contain at least one Japanese character (Hiragana, Katakana, or Kanji)
    # Japanese characters are typically in ranges:
    # Hiragana: 0x3040-0x309F
    # Katakana: 0x30A0-0x30FF  
    # Kanji: 0x4E00-0x9FAF
    # Full-width: 0xFF00-0xFFEF
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
    # Count printable characters
    printable_count = sum(1 for c in text if c.isprintable() or ord(c) > 127)
    if printable_count < len(text) * 0.5:  # At least 50% should be printable
        return False
    
    return True


def extract_strings_from_bin(bin_data: bytes) -> List[str]:
    """Extract all Japanese strings from a .bin file
    Handles gzip-compressed files automatically"""
    import gzip
    
    # Check if file is gzip-compressed (starts with 1f 8b)
    if len(bin_data) >= 2 and bin_data[0] == 0x1f and bin_data[1] == 0x8b:
        try:
            # Decompress gzip data
            bin_data = gzip.decompress(bin_data)
        except Exception as e:
            print(f"    Warning: Failed to decompress gzip data: {e}")
            return []
    
    strings = []
    
    # Scan the entire file for null-terminated strings
    pos = 0
    current_string = b""
    
    while pos < len(bin_data):
        byte = bin_data[pos]
        
        if byte == 0:
            # End of string
            if len(current_string) > 0:
                try:
                    decoded = current_string.decode("euc-jp")
                    # Only add if it's valid Japanese text
                    if is_valid_japanese_text(decoded):
                        strings.append(decoded.strip())
                except UnicodeDecodeError:
                    # Not a valid string, skip
                    pass
            current_string = b""
        else:
            # Add byte to current string
            current_string += bytes([byte])
        
        pos += 1
    
    # Handle last string if file doesn't end with null
    if len(current_string) > 0:
        try:
            decoded = current_string.decode("euc-jp")
            if is_valid_japanese_text(decoded):
                strings.append(decoded.strip())
        except UnicodeDecodeError:
            pass
    
    # Remove duplicates while preserving order
    seen = set()
    unique_strings = []
    for s in strings:
        # Normalize whitespace for comparison
        normalized = s.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique_strings.append(normalized)
    
    return unique_strings


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract quest text from qtext.arc or 0000.bin and create XML templates")
    parser.add_argument("--arc", help="Path to qtext.arc file")
    parser.add_argument("--bin", help="Path to extracted 0000.bin file (alternative to --arc)")
    parser.add_argument("--out", default="2_translated/quest", help="Path to output XML directory")
    args = parser.parse_args()

    if not args.arc and not args.bin:
        print("ERROR: Must provide either --arc or --bin")
        return
    
    out_dir = Path(args.out)
    bin_data = None
    bin_name = "0000.bin"
    
    # Handle direct .bin file
    if args.bin:
        bin_path = Path(args.bin)
        if not bin_path.exists():
            print(f"ERROR: BIN file not found: {bin_path}")
            return
        print(f"Processing {bin_path.name}...")
        with bin_path.open("rb") as f:
            bin_data = f.read()
        bin_name = bin_path.name
    # Handle ARC file
    elif args.arc:
        arc_path = Path(args.arc)
        if not arc_path.exists():
            print(f"ERROR: ARC file not found: {arc_path}")
            return
        print(f"Processing {arc_path.name}...")
        try:
            alignment, entries = read_arc(arc_path)
            for entry in entries:
                if entry.name.lower().endswith(".bin"):
                    print(f"  Found {entry.name}")
                    bin_data = entry.data
                    bin_name = entry.name
                    break
            if bin_data is None:
                print("  ERROR: No .bin file found in ARC")
                return
        except Exception as e:
            print(f"  ERROR processing {arc_path.name}: {e}")
            import traceback
            traceback.print_exc()
            return
    
    # Extract strings from .bin file
    strings = extract_strings_from_bin(bin_data)
    
    if len(strings) == 0:
        print(f"    Warning: No strings found in {bin_name}")
        return
    
    print(f"    Extracted {len(strings)} strings")
    
    # Create translation entries
    tr_entries = []
    for idx, string in enumerate(strings):
        tr_entries.append(trEntry(
            jp_text=string,
            en_text="",
            notes="",
            id=idx,
            status="To Do"
        ))
    
    # Create XML
    xml_data = makeXml(tr_entries, friendly_name=f"{bin_name}")
    
    # Write XML file
    out_dir.mkdir(parents=True, exist_ok=True)
    xml_path = out_dir / Path(bin_name).with_suffix(".xml")
    
    with xml_path.open("wb") as f:
        f.write(xml_data)
    
    print(f"    Created: {xml_path}")


if __name__ == "__main__":
    main()

