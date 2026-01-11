#!/usr/bin/env python3
"""
REPLACE-EBOOT - Standalone script
Simple script to replace EBOOT.BIN in a PSP UMD ISO
"""

import sys
from pathlib import Path
import subprocess

def replace_eboot(iso_path: str, eboot_path: str, umd_script: str = None):
    """Replace EBOOT.BIN in the ISO"""
    iso_file = Path(iso_path).resolve()
    eboot_file = Path(eboot_path).resolve()
    
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
    
    if not eboot_file.exists():
        print(f"ERROR: EBOOT.BIN not found: {eboot_file}")
        return False
    
    print("Replacing EBOOT.BIN in ISO...")
    print(f"  ISO:   {iso_file}")
    print(f"  EBOOT: {eboot_file}")
    print(f"  Target: PSP_GAME/SYSDIR/EBOOT.BIN")
    print()
    
    try:
        cmd = [
            sys.executable,
            str(umd_script),
            str(iso_file),
            "PSP_GAME/SYSDIR/EBOOT.BIN",
            str(eboot_file)
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        if result.stdout:
            print(result.stdout.strip())
        if result.stderr:
            print(result.stderr.strip(), file=sys.stderr)
        
        print()
        print("✓ EBOOT.BIN replaced successfully!")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"✗ FAILED: EBOOT.BIN replacement failed")
        if e.stdout:
            print(f"STDOUT: {e.stdout}")
        if e.stderr:
            print(f"STDERR: {e.stderr}")
        print(f"Exit code: {e.returncode}")
        return False
        
    except Exception as e:
        print(f"✗ ERROR: {e}")
        return False

def main():
    """Main entry point"""
    print("REPLACE-EBOOT - Standalone script")
    print("Simple script to replace EBOOT.BIN in a PSP UMD ISO\n")
    
    if len(sys.argv) < 3:
        print("Usage: python replace-eboot.py <iso_path> <eboot_path> [umd_replace_script]")
        print()
        print("Arguments:")
        print("  iso_path          Path to the ISO file to modify")
        print("  eboot_path        Path to the new EBOOT.BIN file")
        print("  umd_replace_script (Optional) Path to umd_replace.py")
        print("                     Default: tools/UMD-replace/umd_replace.py")
        print()
        print("Example:")
        print('  python replace-eboot.py "build\\RM2_translated.iso" "0_disc\\PSP_GAME\\SYSDIR\\EBOOT.BIN"')
        sys.exit(1)
    
    iso_path = sys.argv[1]
    eboot_path = sys.argv[2]
    umd_script = sys.argv[3] if len(sys.argv) > 3 else None
    
    success = replace_eboot(iso_path, eboot_path, umd_script)
    
    if success:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()

