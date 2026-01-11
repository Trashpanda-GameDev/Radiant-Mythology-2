#!/usr/bin/env python3
"""
APPLY-QUEST - Simple script to replace all quest files in ISO
Uses default paths - just run without arguments
"""

import sys
from pathlib import Path
import subprocess

def replace_file(iso_path: Path, iso_file_path: str, local_file_path: Path, umd_script: Path) -> bool:
    """Replace a single file in the ISO"""
    if not iso_path.exists():
        print(f"ERROR: ISO not found: {iso_path}")
        return False
    
    if not umd_script.exists():
        print(f"ERROR: UMD-replace script not found: {umd_script}")
        return False
    
    if not local_file_path.exists():
        print(f"ERROR: File not found: {local_file_path}")
        return False
    
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


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Replace all quest files in ISO (uses default paths)")
    parser.add_argument("--iso", default="build/RM2_translated.iso", 
                       help="Path to ISO file (default: build/RM2_translated.iso)")
    parser.add_argument("--quest-folder", default="0_disc/PSP_GAME/USRDIR/quest", 
                       help="Path to quest folder (default: 0_disc/PSP_GAME/USRDIR/quest)")
    args = parser.parse_args()
    
    # Resolve paths
    script_dir = Path(__file__).parent
    iso_path = Path(args.iso).resolve()
    quest_folder = Path(args.quest_folder).resolve()
    umd_script = script_dir / "UMD-replace" / "umd_replace.py"
    
    if not quest_folder.exists():
        print(f"ERROR: Quest folder not found: {quest_folder}")
        sys.exit(1)
    
    if not quest_folder.is_dir():
        print(f"ERROR: Quest path is not a directory: {quest_folder}")
        sys.exit(1)
    
    print(f"Replacing quest files in ISO...")
    print(f"  ISO: {iso_path}")
    print(f"  Quest folder: {quest_folder}")
    print(f"  Target: PSP_GAME/USRDIR/quest/...")
    print()
    
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
                    # Skip qtext.arc - it should be rebuilt using quest_apply.py
                    print(f"  Skipping {file_path.name} (should be rebuilt using quest_apply.py)")
                    continue
                # Include other files
                files_to_replace.append(file_path)
    
    if not files_to_replace:
        print("  No files found to replace.")
        sys.exit(1)
    
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
        print(f"  Replacing: {iso_file_path}")
        
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
    else:
        print(f"ERROR {failed_count} file(s) failed to replace.")
        sys.exit(1)


if __name__ == "__main__":
    main()

