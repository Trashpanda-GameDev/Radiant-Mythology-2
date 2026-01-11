#!/usr/bin/env python3
"""
REPLACE-QUEST - Standalone script
Script to replace quest folder files in a PSP UMD ISO
Can replace individual files or all files from a quest folder
"""

import sys
from pathlib import Path
import subprocess

def replace_file(iso_path: str, iso_file_path: str, local_file_path: str, umd_script: str = None):
    """Replace a single file in the ISO"""
    iso_file = Path(iso_path).resolve()
    local_file = Path(local_file_path).resolve()
    
    # Default umd_replace.py location relative to this script
    if umd_script is None:
        script_dir = Path(__file__).parent
        umd_script = script_dir / "UMD-replace" / "umd_replace.py"
    else:
        umd_script = Path(umd_script).resolve()
    
    # Validate paths
    if not iso_file.exists():
        print(f"ERROR: ISO not found: {iso_file}")
        return False
    
    if not umd_script.exists():
        print(f"ERROR: UMD-replace script not found: {umd_script}")
        print(f"Please specify the path to umd_replace.py")
        return False
    
    if not local_file.exists():
        print(f"ERROR: File not found: {local_file}")
        return False
    
    print(f"  Replacing: {iso_file_path}")
    print(f"    Local:   {local_file}")
    
    try:
        cmd = [
            sys.executable,
            str(umd_script),
            str(iso_file),
            iso_file_path,
            str(local_file)
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
        print(f"    ✗ ERROR: {e}")
        return False

def replace_quest_files(iso_path: str, quest_folder_path: str, umd_script: str = None, specific_files: list = None):
    """Replace quest folder files in the ISO"""
    iso_file = Path(iso_path).resolve()
    quest_folder = Path(quest_folder_path).resolve()
    
    # Default umd_replace.py location relative to this script
    if umd_script is None:
        script_dir = Path(__file__).parent
        umd_script = script_dir / "UMD-replace" / "umd_replace.py"
    else:
        umd_script = Path(umd_script).resolve()
    
    # Validate paths
    if not iso_file.exists():
        print(f"ERROR: ISO not found: {iso_file}")
        return False
    
    if not umd_script.exists():
        print(f"ERROR: UMD-replace script not found: {umd_script}")
        print(f"Please specify the path to umd_replace.py")
        return False
    
    if not quest_folder.exists():
        print(f"ERROR: Quest folder not found: {quest_folder}")
        return False
    
    if not quest_folder.is_dir():
        print(f"ERROR: Quest path is not a directory: {quest_folder}")
        return False
    
    print("Replacing quest folder files in ISO...")
    print(f"  ISO:   {iso_file}")
    print(f"  Quest: {quest_folder}")
    print(f"  Target: PSP_GAME/USRDIR/quest/...")
    print()
    
    # Find all files to replace
    files_to_replace = []
    
    if specific_files:
        # Replace only specified files
        for file_name in specific_files:
            file_path = quest_folder / file_name
            if file_path.exists() and file_path.is_file():
                files_to_replace.append(file_path)
            else:
                print(f"  WARNING: File not found: {file_path}")
    else:
        # Replace all files in quest folder (recursively)
        for file_path in quest_folder.rglob("*"):
            if file_path.is_file():
                files_to_replace.append(file_path)
    
    if not files_to_replace:
        print("  No files found to replace.")
        return False
    
    print(f"Found {len(files_to_replace)} file(s) to replace:")
    print()
    
    # Process each file
    success_count = 0
    failed_count = 0
    
    for i, file_path in enumerate(files_to_replace, 1):
        # Get relative path from quest folder
        relative_path = file_path.relative_to(quest_folder)
        
        # Convert to ISO path format
        iso_file_path = f"PSP_GAME/USRDIR/quest/{str(relative_path).replace(chr(92), '/')}"
        
        print(f"[{i}/{len(files_to_replace)}] {relative_path}")
        
        success = replace_file(iso_path, iso_file_path, file_path, umd_script)
        
        if success:
            success_count += 1
        else:
            failed_count += 1
        
        print()  # Add spacing between files
    
    # Summary
    print("=" * 60)
    print(f"Summary: {success_count} succeeded, {failed_count} failed")
    
    if success_count == len(files_to_replace):
        print("OK All quest files replaced successfully!")
        return True
    else:
        print(f"ERROR {failed_count} file(s) failed to replace.")
        return False

def main():
    """Main entry point"""
    print("REPLACE-QUEST - Standalone script")
    print("Script to replace quest folder files in a PSP UMD ISO\n")
    
    if len(sys.argv) < 3:
        print("Usage: python replace-quest.py <iso_path> <quest_folder_path> [file1] [file2] ...")
        print()
        print("Arguments:")
        print("  iso_path          Path to the ISO file to modify")
        print("  quest_folder_path Path to the quest folder (or specific file)")
        print("  [file1] [file2]   (Optional) Specific files to replace")
        print("                     If not specified, replaces all files in quest folder")
        print("  umd_replace_script (Optional) Path to umd_replace.py")
        print("                     Default: tools/UMD-replace/umd_replace.py")
        print()
        print("Examples:")
        print('  # Replace all quest files:')
        print('  python replace-quest.py "build\\RM2_translated.iso" "0_disc\\PSP_GAME\\USRDIR\\quest"')
        print()
        print('  # Replace specific files:')
        print('  python replace-quest.py "build\\RM2_translated.iso" "0_disc\\PSP_GAME\\USRDIR\\quest" "qdata.bin" "qtext.arc"')
        print()
        print('  # Replace a single file:')
        print('  python replace-quest.py "build\\RM2_translated.iso" "0_disc\\PSP_GAME\\USRDIR\\quest\\qdata.bin"')
        sys.exit(1)
    
    iso_path = sys.argv[1]
    quest_path = sys.argv[2]
    
    # Check if quest_path is a file or directory
    quest_path_obj = Path(quest_path)
    
    if quest_path_obj.is_file():
        # Single file replacement
        quest_folder = quest_path_obj.parent
        file_name = quest_path_obj.name
        
        # Get relative path from USRDIR
        usrdir_path = quest_folder.parent.parent / "USRDIR"
        try:
            relative_path = quest_path_obj.relative_to(usrdir_path)
            iso_file_path = f"PSP_GAME/USRDIR/{str(relative_path).replace(chr(92), '/')}"
        except ValueError:
            # Fallback: assume it's in quest folder
            iso_file_path = f"PSP_GAME/USRDIR/quest/{file_name}"
        
        print("Replacing single quest file in ISO...")
        print(f"  ISO:   {iso_path}")
        print(f"  File:  {quest_path_obj}")
        print(f"  Target: {iso_file_path}")
        print()
        
        # Default umd_replace.py location
        script_dir = Path(__file__).parent
        umd_script = script_dir / "UMD-replace" / "umd_replace.py"
        
        success = replace_file(iso_path, iso_file_path, quest_path_obj, umd_script)
        
        if success:
            print()
            print("✓ File replaced successfully!")
            sys.exit(0)
        else:
            sys.exit(1)
    
    else:
        # Folder replacement
        specific_files = None
        umd_script = None
        
        # Check for optional arguments
        if len(sys.argv) > 3:
            # Check if last argument is umd_replace_script (ends with .py)
            if sys.argv[-1].endswith('.py') and Path(sys.argv[-1]).exists():
                umd_script = sys.argv[-1]
                specific_files = sys.argv[3:-1] if len(sys.argv) > 4 else None
            else:
                specific_files = sys.argv[3:]
        
        success = replace_quest_files(iso_path, quest_path, umd_script, specific_files)
        
        if success:
            sys.exit(0)
        else:
            sys.exit(1)

if __name__ == "__main__":
    main()

