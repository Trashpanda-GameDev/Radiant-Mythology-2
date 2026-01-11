#!/usr/bin/env python3
"""
APPLY-EBOOT - Simple script to replace EBOOT.BIN in ISO
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
    
    print(f"Replacing EBOOT.BIN in ISO...")
    print(f"  ISO: {iso_path}")
    print(f"  File: {local_file_path}")
    print(f"  Target: {iso_file_path}")
    
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
            print(f"  {result.stdout.strip()}")
        if result.stderr:
            print(f"  {result.stderr.strip()}", file=sys.stderr)
        
        print(f"\nOK Successfully replaced EBOOT.BIN in ISO!")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"  FAILED")
        if e.stdout:
            print(f"  STDOUT: {e.stdout}")
        if e.stderr:
            print(f"  STDERR: {e.stderr}")
        print(f"  Exit code: {e.returncode}")
        return False
        
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Replace EBOOT.BIN in ISO (uses default paths)")
    parser.add_argument("--iso", default="build/RM2_translated.iso", 
                       help="Path to ISO file (default: build/RM2_translated.iso)")
    parser.add_argument("--eboot", default="0_disc/PSP_GAME/SYSDIR/EBOOT.BIN", 
                       help="Path to EBOOT.BIN file (default: 0_disc/PSP_GAME/SYSDIR/EBOOT.BIN)")
    args = parser.parse_args()
    
    # Resolve paths
    script_dir = Path(__file__).parent
    iso_path = Path(args.iso).resolve()
    eboot_path = Path(args.eboot).resolve()
    umd_script = script_dir / "UMD-replace" / "umd_replace.py"
    
    # Replace EBOOT.BIN
    iso_file_path = "PSP_GAME/SYSDIR/EBOOT.BIN"
    success = replace_file(iso_path, iso_file_path, eboot_path, umd_script)
    
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()

