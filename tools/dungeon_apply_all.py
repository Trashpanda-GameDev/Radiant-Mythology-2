#!/usr/bin/env python3
"""
Rebuild all dungeon ARC files from extracted/modified files
"""

import sys
from pathlib import Path
import subprocess

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Rebuild all dungeon ARC files from extracted/modified files")
    parser.add_argument("--iso", 
                       help="Path to ISO file to update (e.g., build/RM2_translated.iso)")
    parser.add_argument("--no-iso", action="store_true",
                       help="Skip ISO replacement (only rebuild ARC files)")
    args = parser.parse_args()
    
    script_dir = Path(__file__).parent
    apply_script = script_dir / "dungeon_apply.py"
    dungeon_dir = Path("0_disc/PSP_GAME/USRDIR/dungeon")
    extracted_dir = Path("1_extracted/dungeon")
    out_dir = Path("3_patched/PSP_GAME/USRDIR/dungeon")
    
    if not apply_script.exists():
        print(f"ERROR: dungeon_apply.py script not found: {apply_script}")
        sys.exit(1)
    
    if not dungeon_dir.exists():
        print(f"ERROR: Dungeon directory not found: {dungeon_dir}")
        sys.exit(1)
    
    if not extracted_dir.exists():
        print(f"ERROR: Extracted directory not found: {extracted_dir}")
        print(f"Please run extract_all_dungeons.py first")
        sys.exit(1)
    
    # Find all ARC files
    arc_files = sorted(dungeon_dir.glob("*.arc"))
    
    if len(arc_files) == 0:
        print(f"No ARC files found in {dungeon_dir}")
        sys.exit(1)
    
    print(f"Rebuilding {len(arc_files)} dungeon ARC file(s)...")
    print(f"  Source ARC files: {dungeon_dir}")
    print(f"  Extracted files: {extracted_dir}")
    print(f"  Output directory: {out_dir}")
    if args.iso:
        print(f"  ISO file: {args.iso}")
    elif not args.no_iso:
        default_iso = Path("build/RM2_translated.iso")
        if default_iso.exists():
            print(f"  ISO file: {default_iso} (default)")
    print()
    
    success_count = 0
    skipped_count = 0
    failed_count = 0
    failed_files = []
    skipped_files = []
    
    for i, arc_file in enumerate(arc_files, 1):
        arc_name = arc_file.name
        arc_stem = arc_file.stem  # filename without .arc extension
        
        # Check if extracted folder exists
        extracted_subfolder = extracted_dir / arc_stem
        if not extracted_subfolder.exists():
            print(f"[{i}/{len(arc_files)}] Skipping {arc_name} - extracted folder not found: {extracted_subfolder}")
            skipped_count += 1
            skipped_files.append(arc_name)
            print()
            continue
        
        # Check if extracted folder has any files
        extracted_files = list(extracted_subfolder.iterdir())
        if not extracted_files:
            print(f"[{i}/{len(arc_files)}] Skipping {arc_name} - extracted folder is empty: {extracted_subfolder}")
            skipped_count += 1
            skipped_files.append(arc_name)
            print()
            continue
        
        print(f"[{i}/{len(arc_files)}] Rebuilding {arc_name}...")
        
        try:
            cmd = [
                sys.executable,
                str(apply_script),
                "--arc", str(arc_file),
                "--extracted", str(extracted_dir),
                "--pad-size"
            ]
            
            # Add ISO parameter if provided
            if args.iso:
                cmd.extend(["--iso", str(args.iso)])
            elif not args.no_iso:
                # Use default ISO path
                default_iso = Path("build/RM2_translated.iso")
                if default_iso.exists():
                    cmd.extend(["--iso", str(default_iso)])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            # Show key output lines
            if result.stdout:
                lines = result.stdout.strip().split('\n')
                # Show summary line if available
                for line in lines:
                    if "Summary:" in line or "OK Created patched ARC" in line or "Size verified" in line:
                        print(f"  {line}")
            
            success_count += 1
            print()
            
        except subprocess.CalledProcessError as e:
            print(f"  ERROR: Failed to rebuild {arc_name}")
            if e.stdout:
                # Show last few lines of output
                lines = e.stdout.strip().split('\n')
                for line in lines[-3:]:
                    if line.strip():
                        print(f"  {line}")
            if e.stderr:
                print(f"  STDERR: {e.stderr.strip()}")
            failed_count += 1
            failed_files.append(arc_name)
            print()
        
        except Exception as e:
            print(f"  ERROR: {e}")
            failed_count += 1
            failed_files.append(arc_name)
            print()
    
    # Summary
    print("=" * 60)
    print(f"Summary:")
    print(f"  Successfully rebuilt: {success_count}")
    print(f"  Skipped (no extracted files): {skipped_count}")
    print(f"  Failed: {failed_count}")
    
    if skipped_files:
        print(f"\nSkipped files (no extracted folder/files found):")
        for name in skipped_files:
            print(f"  - {name}")
    
    if failed_files:
        print(f"\nFailed files:")
        for name in failed_files:
            print(f"  - {name}")
    
    if failed_count == 0 and success_count > 0:
        print(f"\nOK All dungeon ARC files rebuilt successfully!")
        print(f"  Output: {out_dir}")
    elif failed_count > 0:
        print(f"\nWARNING: {failed_count} file(s) failed to rebuild")
        sys.exit(1)
    else:
        print(f"\nNo files were rebuilt (all skipped)")
        sys.exit(1)


if __name__ == "__main__":
    main()
