#!/usr/bin/env python3
"""
REPLACE-SPECIFIC - Python version
Single file replacement tool for PSP UMD ISO images
Based on the replace-all.py functionality but for individual files
"""

import os
import sys
import glob
from pathlib import Path
from typing import List, Tuple, Optional
import subprocess

# Import configuration from config.py
try:
    from config import ISO_PATH, UMD_REPLACE_SCRIPT, USRDIR_PATH
except ImportError:
    print("ERROR: config.py not found!")
    print("Please create config.py with your paths and settings.")
    print("See config.py.example for a template.")
    sys.exit(1)

class SpecificReplacer:
    def __init__(self, iso_path: str, umd_script: str, usrdir_path: str):
        self.iso_path = Path(iso_path).resolve()
        self.umd_script = Path(umd_script).resolve()
        self.usrdir_path = Path(usrdir_path).resolve()
        
        # Validate paths
        self._validate_paths()
    
    def _validate_paths(self):
        """Validate that all required paths exist"""
        if not self.iso_path.exists():
            raise FileNotFoundError(f"ISO not found: {self.iso_path}")
        
        if not self.umd_script.exists():
            raise FileNotFoundError(f"UMD-replace script not found: {self.umd_script}")
        
        if not self.usrdir_path.exists():
            raise FileNotFoundError(f"USRDIR not found: {self.usrdir_path}")
        
        if not self.usrdir_path.is_dir():
            raise NotADirectoryError(f"USRDIR is not a directory: {self.usrdir_path}")
    
    def get_relative_path(self, file_path: Path) -> str:
        """Get the relative path from USRDIR to the file"""
        try:
            return file_path.relative_to(self.usrdir_path)
        except ValueError:
            # If file is not under USRDIR, return the full path
            return str(file_path)
    
    def get_iso_path(self, relative_path: str) -> str:
        """Convert relative path to ISO internal path"""
        # Convert Windows path separators to forward slashes for ISO
        iso_path = str(relative_path).replace('\\', '/')
        # Ensure it starts with PSP_GAME/USRDIR
        if not iso_path.startswith('PSP_GAME/USRDIR/'):
            iso_path = f"PSP_GAME/USRDIR/{iso_path}"
        return iso_path
    
    def replace_file(self, file_path: Path) -> Tuple[bool, Optional[dict]]:
        """Replace a single file in the ISO using umd-replace.py"""
        try:
            # Get relative path and ISO path
            relative_path = self.get_relative_path(file_path)
            iso_path = self.get_iso_path(relative_path)
            
            print(f"-> {iso_path}")
            
            # Build command
            cmd = [
                sys.executable,  # Use current Python interpreter
                str(self.umd_script),
                str(self.iso_path),
                iso_path,
                str(file_path)
            ]
            
            # Run the command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            # Print output
            if result.stdout:
                print(result.stdout.strip())
            if result.stderr:
                print(result.stderr.strip(), file=sys.stderr)
            
            return True, None
            
        except subprocess.CalledProcessError as e:
            print(f"FAILED: {iso_path}")
            if e.stdout:
                print(f"STDOUT: {e.stdout}")
            if e.stderr:
                print(f"STDERR: {e.stderr}")
            print(f"Exit code: {e.returncode}")
            
            # Return error details
            error_info = {
                'error_type': 'subprocess_error',
                'exit_code': e.returncode,
                'stdout': e.stdout.strip() if e.stdout else '',
                'stderr': e.stderr.strip() if e.stderr else '',
                'command': ' '.join(cmd)
            }
            return False, error_info
            
        except Exception as e:
            print(f"ERROR processing {file_path}: {e}")
            
            # Return error details
            error_info = {
                'error_type': 'exception',
                'error_message': str(e),
                'error_class': type(e).__name__
            }
            return False, error_info

def main():
    """Main entry point"""
    print("REPLACE-SPECIFIC - Python version")
    print("Single or multiple file replacement tool for PSP UMD ISO images\n")
    
    # Check command line arguments
    if len(sys.argv) < 2:
        print("Usage: python tools/replace-specific.py <file_path1> [file_path2] [file_path3] ...")
        print("Example: python tools/replace-specific.py facechat\\ev0000.arc")
        print("Example: python tools/replace-specific.py npc\\mapShip_g1.arc")
        print("Example: python tools/replace-specific.py facechat\\ev0000.arc npc\\mapShip_g1.arc")
        sys.exit(1)
    
    # Get all file paths from command line arguments
    target_files = sys.argv[1:]
    
    print(f"Processing {len(target_files)} file(s)...")
    print()
    
    # Process each file
    success_count = 0
    failed_count = 0
    failed_files = []
    
    for i, target_file in enumerate(target_files, 1):
        print(f"[{i}/{len(target_files)}] Processing: {target_file}")
        
        target_path = Path(target_file)
        
        # If it's a relative path, make it relative to USRDIR
        if not target_path.is_absolute():
            target_path = Path(USRDIR_PATH) / target_file
        
        # Resolve the full path
        target_path = target_path.resolve()
        
        print(f"  Full path: {target_path}")
        
        # Validate the target file exists
        if not target_path.exists():
            print(f"  ERROR: Target file not found: {target_path}")
            failed_count += 1
            failed_files.append({
                'file': target_file,
                'error': 'File not found'
            })
            continue
        
        if not target_path.is_file():
            print(f"  ERROR: Target is not a file: {target_path}")
            failed_count += 1
            failed_files.append({
                'file': target_file,
                'error': 'Not a file'
            })
            continue
        
        # Check if the file is under USRDIR
        try:
            relative_path = target_path.relative_to(USRDIR_PATH)
            print(f"  Relative path: {relative_path}")
        except ValueError:
            print(f"  WARNING: File is not under USRDIR: {target_path}")
            print(f"  USRDIR: {USRDIR_PATH}")
            print("  This might cause issues with the replacement.")
        
        try:
            # Create replacer instance
            replacer = SpecificReplacer(
                iso_path=ISO_PATH,
                umd_script=UMD_REPLACE_SCRIPT,
                usrdir_path=USRDIR_PATH
            )
            
            # Replace the specific file
            print("  Replacing file...")
            success, error_info = replacer.replace_file(target_path)
            
            if success:
                print("  ✓ File replaced successfully!")
                success_count += 1
            else:
                print("  ✗ File replacement failed.")
                failed_count += 1
                
                # Store failed file info
                failed_files.append({
                    'file': target_file,
                    'error': 'Replacement failed',
                    'error_info': error_info
                })
                
        except Exception as e:
            print(f"  ✗ ERROR processing {target_file}: {e}")
            failed_count += 1
            failed_files.append({
                'file': target_file,
                'error': f'Exception: {e}'
            })
        
        print()  # Add spacing between files
    
    # Summary
    print("=" * 60)
    print(f"Summary: {success_count} succeeded, {failed_count} failed")
    
    if failed_files:
        print("\nFailed files:")
        for failed in failed_files:
            print(f"  {failed['file']}: {failed['error']}")
            if 'error_info' in failed and failed['error_info']:
                error_info = failed['error_info']
                if error_info['error_type'] == 'subprocess_error':
                    print(f"    Exit code: {error_info['exit_code']}")
                    if error_info['stderr']:
                        print(f"    STDERR: {error_info['stderr']}")
                elif error_info['error_type'] == 'exception':
                    print(f"    {error_info['error_class']}: {error_info['error_message']}")
    
    if failed_count == 0:
        print("\nAll files replaced successfully!")
        sys.exit(0)
    else:
        print(f"\n{failed_count} file(s) failed to replace.")
        sys.exit(1)

if __name__ == "__main__":
    main()
