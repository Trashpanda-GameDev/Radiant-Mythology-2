#!/usr/bin/env python3
"""
UMD-REPLACE - Python version
Tiny tool to replace data files in a PSP UMD ISO
Based on the original C implementation by CUE (2012-2015)
"""

import os
import sys
import struct
from pathlib import Path
from typing import Tuple, Optional

# Constants from the original C code
VERSION = "20241201"
DESCRIPTOR_LBA = 0x010
TOTAL_SECTORS = 0x050
ROOT_FOLDER_LBA = 0x09E
ROOT_SIZE = 0x0A6
TABLE_PATH_LEN = 0x084
TABLE_PATH_LBA = 0x08C

DESCRIPTOR_SIG_1 = 0x0001313030444301
DESCRIPTOR_SIG_2 = 0x00013130304443FF

LEN_SECTOR_M0 = 0x800
LEN_DATA_M0 = 0x800
POS_DATA_M0 = 0x000

TMPNAME = "umd-replace.tmp"
BLOCKSIZE = 16384

class UMDReplacer:
    def __init__(self):
        self.sector_size = LEN_SECTOR_M0
        self.data_offset = POS_DATA_M0
        self.sector_data = LEN_DATA_M0
    
    def file_size(self, filename: str) -> int:
        """Get file size in bytes"""
        return os.path.getsize(filename)
    
    def read_file(self, filename: str, position: int, length: int) -> bytes:
        """Read bytes from file at specific position"""
        with open(filename, 'rb') as f:
            f.seek(position)
            return f.read(length)
    
    def write_file(self, filename: str, position: int, data: bytes):
        """Write bytes to file at specific position"""
        with open(filename, 'r+b') as f:
            f.seek(position)
            f.write(data)
    
    def create_file(self, filename: str):
        """Create empty file"""
        with open(filename, 'wb') as f:
            pass
    
    def resolve_path(self, path: str) -> str:
        """Resolve relative path to absolute path"""
        return str(Path(path).resolve())
    
    def change_endian(self, value: int) -> int:
        """Change endianness of 32-bit value"""
        return struct.unpack('<I', struct.pack('>I', value))[0]
    
    def read_sectors(self, filename: str, lba: int, sectors: int) -> bytes:
        """Read sectors from ISO file"""
        return self.read_file(filename, lba * self.sector_size, sectors * self.sector_size)
    
    def write_sectors(self, filename: str, lba: int, data: bytes, sectors: int):
        """Write sectors to ISO file"""
        self.write_file(filename, lba * self.sector_size, data)
    
    def search_file(self, isoname: str, filename: str, path: str, lba: int, length: int) -> Optional[int]:
        """Search for file in ISO directory structure"""
        total_sectors = (length + LEN_SECTOR_M0 - 1) // LEN_SECTOR_M0
        
        for i in range(total_sectors):
            buffer = self.read_sectors(isoname, lba + i, 1)
            pos = 0
            
            while pos < self.sector_data:
                # Field size
                nbytes = buffer[self.data_offset + pos]
                if nbytes == 0:
                    break
                
                # Name size
                nchars = buffer[self.data_offset + pos + 0x020]
                name = buffer[self.data_offset + pos + 0x021:self.data_offset + pos + 0x021 + nchars].decode('ascii', errors='ignore')
                
                # Discard the ";1" final
                if nchars > 2 and name.endswith(';1'):
                    name = name[:-2]
                    nchars -= 2
                
                # Check name except for '.' and '..' entries
                if nchars != 1 or (name and name != '\x00' and name != '\x01'):
                    newpath = f"{path}/{name}" if path else f"/{name}"
                    
                    # Recursive search in folders
                    if buffer[self.data_offset + pos + 0x019] & 0x02:
                        newlba = struct.unpack('<I', buffer[self.data_offset + pos + 0x002:self.data_offset + pos + 0x006])[0]
                        newlen = struct.unpack('<I', buffer[self.data_offset + pos + 0x00A:self.data_offset + pos + 0x00E])[0]
                        
                        found = self.search_file(isoname, filename, newpath, newlba, newlen)
                        if found:
                            return found
                    else:
                        # Compare names - case insensitive
                        if filename.lower() == newpath.lower():
                            return (lba + i) * self.sector_size + self.data_offset + pos
                
                # Point to next entry
                pos += nbytes
        
        return None
    
    def update_path_table(self, isoname: str, lba: int, length: int, lba_old: int, diff: int, swap_endian: bool):
        """Update path table entries"""
        total_sectors = (length + LEN_SECTOR_M0 - 1) // LEN_SECTOR_M0
        buffer = bytearray(self.read_sectors(isoname, lba, total_sectors))
        
        change = False
        pos = 0
        
        while pos < length:
            nbytes = buffer[self.data_offset + pos]
            if nbytes == 0:
                break
            
            # Position
            newlba = struct.unpack('<I', buffer[self.data_offset + pos + 0x002:self.data_offset + pos + 0x006])[0]
            if swap_endian:
                newlba = self.change_endian(newlba)
            
            # Update needed?
            if newlba > lba_old:
                change = True
                newlba += diff
                if swap_endian:
                    newlba = self.change_endian(newlba)
                
                # Write back the updated LBA
                lba_bytes = struct.pack('<I', newlba)
                buffer[self.data_offset + pos + 0x002:self.data_offset + pos + 0x006] = lba_bytes
            
            pos += 0x08 + nbytes + (nbytes & 0x1)
        
        # Update sectors if needed
        if change:
            self.write_sectors(isoname, lba, buffer, total_sectors)
    
    def update_toc(self, isoname: str, lba: int, length: int, found: int, lba_old: int, diff: int):
        """Update table of contents entries"""
        total_sectors = (length + LEN_SECTOR_M0 - 1) // LEN_SECTOR_M0
        
        for i in range(total_sectors):
            buffer = bytearray(self.read_sectors(isoname, lba + i, 1))
            change = False
            pos = 0
            
            while pos < length:
                nbytes = buffer[self.data_offset + pos]
                if nbytes == 0:
                    break
                
                # Name size
                nchars = buffer[self.data_offset + pos + 0x020]
                name = buffer[self.data_offset + pos + 0x021:self.data_offset + pos + 0x021 + nchars].decode('ascii', errors='ignore')
                
                # Position
                newlba = struct.unpack('<I', buffer[self.data_offset + pos + 0x002:self.data_offset + pos + 0x006])[0]
                
                # Needed to change a 0-bytes file with more 0-bytes files (same LBA)
                newfound = (lba + i) * self.sector_size + self.data_offset + pos
                
                # Update needed?
                if (newlba > lba_old) or ((newlba == lba_old) and (newfound > found)):
                    change = True
                    newlba += diff
                    j = self.change_endian(newlba)
                    
                    # Update both little and big endian versions
                    lba_bytes = struct.pack('<I', newlba)
                    buffer[self.data_offset + pos + 0x002:self.data_offset + pos + 0x006] = lba_bytes
                    buffer[self.data_offset + pos + 0x006:self.data_offset + pos + 0x00A] = struct.pack('<I', j)
                
                # Check name except for '.' and '..' entries
                if nchars != 1 or (name and name != '\x00' and name != '\x01'):
                    # Recursive update in folders
                    if buffer[self.data_offset + pos + 0x019] & 0x02:
                        newlen = struct.unpack('<I', buffer[self.data_offset + pos + 0x00A:self.data_offset + pos + 0x00E])[0]
                        self.update_toc(isoname, newlba, newlen, found, lba_old, diff)
                
                # Point to next entry
                pos += nbytes
            
            # Update sector if needed
            if change:
                self.write_sectors(isoname, lba + i, buffer, 1)
    
    def replace_file(self, isoname: str, oldname: str, newname: str):
        """Main function to replace file in ISO"""
        print(f"Replacing '{oldname}' with '{newname}' in '{isoname}'")
        
        # Get data from the primary volume descriptor
        buffer = self.read_sectors(isoname, DESCRIPTOR_LBA, 1)
        
        image_sectors = struct.unpack('<I', buffer[self.data_offset + TOTAL_SECTORS:self.data_offset + TOTAL_SECTORS + 4])[0]
        total_sectors = self.file_size(isoname) // self.sector_size
        root_lba = struct.unpack('<I', buffer[self.data_offset + ROOT_FOLDER_LBA:self.data_offset + ROOT_FOLDER_LBA + 4])[0]
        root_length = struct.unpack('<I', buffer[self.data_offset + ROOT_SIZE:self.data_offset + ROOT_SIZE + 4])[0]
        
        # Get new data from the new file
        new_filesize = self.file_size(newname)
        new_sectors = (new_filesize + self.sector_data - 1) // self.sector_data
        
        # 'oldname' must start with a path separator
        if not oldname.startswith('/') and not oldname.startswith('\\'):
            oldname = '/' + oldname
        
        # Change all backslashes by slashes in 'oldname'
        oldname = oldname.replace('\\', '/')
        
        # Search 'oldname' in the image
        found_position = self.search_file(isoname, oldname, "", root_lba, root_length)
        if found_position is None:
            print(f"File not found in the UMD image: {oldname}")
            sys.exit(1)
        
        found_lba = found_position // self.sector_size
        found_offset = found_position % self.sector_size
        
        # Get data from the old file
        buffer = self.read_sectors(isoname, found_lba, 1)
        
        old_filesize = struct.unpack('<I', buffer[found_offset + 0x0A:found_offset + 0x0E])[0]
        old_sectors = (old_filesize + self.sector_data - 1) // self.sector_data
        file_lba = struct.unpack('<I', buffer[found_offset + 0x02:found_offset + 0x06])[0]
        
        # Size difference in sectors
        diff = new_sectors - old_sectors
        
        # Image name
        name = TMPNAME if old_sectors != new_sectors else isoname
        
        if diff:
            # Create the new image
            print("- creating temporal image")
            self.create_file(name)
            
            lba = 0
            
            # Update the previous sectors
            print("- updating previous data sectors")
            maxim = file_lba
            i = 0
            while i < file_lba:
                count = min(maxim, BLOCKSIZE)
                maxim -= count
                
                buffer = self.read_sectors(isoname, i, count)
                self.write_sectors(name, lba, buffer, count)
                lba += count
                
                i += count
        else:
            lba = file_lba
        
        # Update the new file
        print("- updating file data")
        
        if new_sectors:
            # Read and update all data sectors except the latest one (maybe incomplete)
            maxim = new_sectors - 1
            i = 0
            while i < maxim:
                count = min(maxim, BLOCKSIZE)
                maxim -= count
                
                buffer = bytearray(count * self.sector_size)
                tmp = self.read_file(newname, i * self.sector_data, count * self.sector_data)
                
                for j in range(count):
                    for k in range(self.sector_data):
                        if j * self.sector_data + k < len(tmp):
                            buffer[j * self.sector_size + self.data_offset + k] = tmp[j * self.sector_data + k]
                
                self.write_sectors(name, lba, bytes(buffer), count)
                lba += count
                i += count
            
            new_sectors = i + 1
            
            # Read and update the remaining data sector
            new_length = new_filesize - i * self.sector_data
            
            buffer = bytearray(self.sector_size)
            tmp = self.read_file(newname, i * self.sector_data, new_length)
            for j in range(new_length):
                buffer[self.data_offset + j] = tmp[j]
            
            self.write_sectors(name, lba, bytes(buffer), 1)
            lba += 1
        
        if diff:
            # Update the next sectors
            print("- updating next data sectors")
            maxim = total_sectors - (file_lba + old_sectors)
            i = file_lba + old_sectors
            while i < total_sectors:
                count = min(maxim, BLOCKSIZE)
                maxim -= count
                
                buffer = self.read_sectors(isoname, i, count)
                self.write_sectors(name, lba, buffer, count)
                lba += count
                
                i += count
        
        if new_filesize != old_filesize:
            # Update the file size
            print("- updating file size")
            
            l_endian = new_filesize
            b_endian = self.change_endian(l_endian)
            
            buffer = bytearray(self.read_sectors(name, found_lba, 1))
            struct.pack_into('<I', buffer, found_offset + 0x0A, l_endian)
            struct.pack_into('<I', buffer, found_offset + 0x0E, b_endian)
            self.write_sectors(name, found_lba, bytes(buffer), 1)
        
        if diff:
            # Update the primary volume descriptor
            print("- updating primary volume descriptor")
            
            l_endian = image_sectors + diff
            b_endian = self.change_endian(l_endian)
            
            buffer = bytearray(self.read_sectors(name, DESCRIPTOR_LBA, 1))
            struct.pack_into('<I', buffer, self.data_offset + TOTAL_SECTORS, l_endian)
            struct.pack_into('<I', buffer, self.data_offset + TOTAL_SECTORS + 4, b_endian)
            self.write_sectors(name, DESCRIPTOR_LBA, buffer, 1)
            
            # Update the path tables
            print("- updating path tables")
            
            buffer = self.read_sectors(name, DESCRIPTOR_LBA, 1)
            for i in range(4):
                tbl_len = struct.unpack('<I', buffer[self.data_offset + TABLE_PATH_LEN:self.data_offset + TABLE_PATH_LEN + 4])[0]
                tbl_lba = struct.unpack('<I', buffer[self.data_offset + TABLE_PATH_LBA + 4*i:self.data_offset + TABLE_PATH_LBA + 4*i + 4])[0]
                if tbl_lba:
                    if i & 0x2:
                        tbl_lba = self.change_endian(tbl_lba)
                    self.update_path_table(name, tbl_lba, tbl_len, file_lba, diff, i & 0x2)
            
            # Update the file/folder LBAs
            print("- updating entire TOCs")
            self.update_toc(name, root_lba, root_length, found_position, file_lba, diff)
            
            # Remove the old image
            print("- removing old image")
            try:
                os.remove(isoname)
            except OSError as e:
                print(f"Remove file error: {isoname} - {e}")
                sys.exit(1)
            
            # Rename the new image
            print("- renaming temporal image")
            try:
                os.rename(name, isoname)
            except OSError as e:
                print(f"Rename file error: {name} -> {isoname} - {e}")
                sys.exit(1)
        
        print(f"- the new image has ", end="")
        if diff > 0:
            print(f"{diff} more", end="")
        elif diff < 0:
            print(f"{-diff} fewer", end="")
        else:
            print("the same", end="")
        
        print(" sector", end="")
        if abs(diff) != 1:
            print("s", end="")
        
        if not diff:
            print(" as", end="")
        else:
            print(" than", end="")
        
        print(" the original image")
        
        if diff:
            print("- maybe you need to hand update the cuesheet file (if exist and needed)")

def main():
    """Main entry point"""
    print(f"\nUMD-REPLACE version {VERSION} - Python version")
    print("Tiny tool to replace data files in a PSP UMD ISO\n")
    
    if len(sys.argv) != 4:
        print("Usage: umd_replace.py imagename filename newfile")
        print("\n- 'imagename' is the name of the UMD image")
        print("- 'filename' is the file in the UMD image with the data to be replaced")
        print("- 'newfile' is the file with the new data")
        print("\n* 'imagename' must be a valid UMD ISO image")
        print("* 'filename' can use either the slash or backslash")
        print("* 'newfile' can be different size as 'filename'")
        sys.exit(1)
    
    # Resolve relative paths to absolute paths (only for actual files)
    isoname = sys.argv[1]
    oldname = sys.argv[2]  # Internal ISO path - don't resolve
    newname = sys.argv[3]
    
    replacer = UMDReplacer()
    
    # Resolve paths
    resolved_iso = replacer.resolve_path(isoname)
    resolved_new = replacer.resolve_path(newname)
    
    print("Resolved paths:")
    print(f"  ISO: {resolved_iso}")
    print(f"  Old: {oldname} (internal ISO path)")
    print(f"  New: {resolved_new}")
    print()
    
    try:
        replacer.replace_file(resolved_iso, oldname, resolved_new)
        print("\nDone")
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
