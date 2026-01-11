#!/usr/bin/env python3
"""
Extract all dungeon ARC files
"""

import sys
from pathlib import Path
import subprocess

def main():
    script_dir = Path(__file__).parent
    extract_script = script_dir / "quest_extract_arc.py"
    dungeon_dir = Path("0_disc/PSP_GAME/USRDIR/dungeon")
    out_dir = Path("1_extracted/dungeon")
    
    if not extract_script.exists():
        print(f"ERROR: Extraction script not found: {extract_script}")
        sys.exit(1)
    
    if not dungeon_dir.exists():
        print(f"ERROR: Dungeon directory not found: {dungeon_dir}")
        sys.exit(1)
    
    # Find all ARC files
    arc_files = sorted(dungeon_dir.glob("*.arc"))
    
    if len(arc_files) == 0:
        print(f"No ARC files found in {dungeon_dir}")
        sys.exit(1)
    
    print(f"Found {len(arc_files)} ARC file(s) to extract")
    print(f"Output directory: {out_dir}")
    print()
    
    success_count = 0
    failed_count = 0
    failed_files = []
    
    for i, arc_file in enumerate(arc_files, 1):
        print(f"[{i}/{len(arc_files)}] Extracting {arc_file.name}...")
        
        try:
            cmd = [
                sys.executable,
                str(extract_script),
                "--arc", str(arc_file),
                "--out", str(out_dir)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            if result.stdout:
                # Show last line (usually "OK Extraction complete!")
                lines = result.stdout.strip().split('\n')
                if lines:
                    print(f"  {lines[-1]}")
            
            success_count += 1
            print()
            
        except subprocess.CalledProcessError as e:
            print(f"  ERROR: Failed to extract {arc_file.name}")
            if e.stdout:
                print(f"  STDOUT: {e.stdout}")
            if e.stderr:
                print(f"  STDERR: {e.stderr}")
            failed_count += 1
            failed_files.append(arc_file.name)
            print()
        
        except Exception as e:
            print(f"  ERROR: {e}")
            failed_count += 1
            failed_files.append(arc_file.name)
            print()
    
    # Summary
    print("=" * 60)
    print(f"Summary: {success_count} succeeded, {failed_count} failed")
    
    if failed_files:
        print(f"\nFailed files:")
        for name in failed_files:
            print(f"  - {name}")
    
    if success_count == len(arc_files):
        print("\nOK All dungeon ARC files extracted successfully!")
    else:
        print(f"\nWARNING: {failed_count} file(s) failed to extract")
        sys.exit(1)


if __name__ == "__main__":
    main()
