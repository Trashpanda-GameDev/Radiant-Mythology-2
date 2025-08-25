#!/usr/bin/env python3
"""
REPLACE-ALL - Python version
Bulk file replacement tool for PSP UMD ISO images
Based on the original replace-all.bat functionality
"""

import os
import sys
import glob
from pathlib import Path
from typing import List, Tuple, Optional
import subprocess

# Import configuration from config.py
try:
    from config import ISO_PATH, UMD_REPLACE_SCRIPT, USRDIR_PATH, FILE_GLOBS
except ImportError:
    print("ERROR: config.py not found!")
    print("Please create config.py with your paths and settings.")
    print("See config.py.example for a template.")
    sys.exit(1)

class BulkReplacer:
    def __init__(self, iso_path: str, umd_script: str, usrdir_path: str, file_globs: list = None):
        self.iso_path = Path(iso_path).resolve()
        self.umd_script = Path(umd_script).resolve()
        self.usrdir_path = Path(usrdir_path).resolve()
        self.file_globs = file_globs or ["*.arc"]
        
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
    
    def find_files(self) -> List[Path]:
        """Find all files matching the glob patterns in USRDIR"""
        all_files = []
        
        for file_glob in self.file_globs:
            pattern = self.usrdir_path / "**" / file_glob
            files = list(Path(self.usrdir_path).rglob(file_glob))
            
            # Filter out directories (in case glob matches directories)
            files = [f for f in files if f.is_file()]
            all_files.extend(files)
        
        # Remove duplicates and sort
        return sorted(set(all_files))
    
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
    
    def replace_all(self) -> bool:
        """Replace all matching files in the ISO"""
        print("Replacing under:")
        print(f"  Local: {self.usrdir_path}")
        print(f"  ISO:   PSP_GAME\\USRDIR\\...")
        print()
        
        # Find all files to replace
        files = self.find_files()
        
        if not files:
            print(f"No files found matching patterns: {', '.join(self.file_globs)}")
            return True
        
        print(f"Found {len(files)} files to replace:")
        for f in files:
            print(f"  {f}")
        print()
        
        # Process each file
        success_count = 0
        failed_count = 0
        failed_files = []  # Track failed files
        
        for i, file_path in enumerate(files, 1):
            print(f"[{i}/{len(files)}] Processing: {file_path.name}")
            
            success, error_info = self.replace_file(file_path)
            if success:
                success_count += 1
            else:
                failed_count += 1
                # Store failed file info with error details
                relative_path = self.get_relative_path(file_path)
                iso_path = self.get_iso_path(relative_path)
                failed_files.append({
                    'local_path': str(file_path),
                    'iso_path': iso_path,
                    'relative_path': str(relative_path),
                    'error_info': error_info
                })
                # Optionally continue or stop on first failure
                # Uncomment the next line to stop on first failure:
                # return False
        
        print()
        print(f"All done. Success: {success_count}, Failed: {failed_count}")
        
        # Display failed files if any
        if failed_files:
            print("\nFailed files:")
            print("=" * 80)
            for failed in failed_files:
                print(f"Local: {failed['local_path']}")
                print(f"ISO:   {failed['iso_path']}")
                print(f"Rel:   {failed['relative_path']}")
                
                # Display error details
                error_info = failed['error_info']
                if error_info:
                    if error_info['error_type'] == 'subprocess_error':
                        print(f"Error: Subprocess failed (exit code: {error_info['exit_code']})")
                        if error_info['stderr']:
                            print(f"STDERR: {error_info['stderr']}")
                        if error_info['stdout']:
                            print(f"STDOUT: {error_info['stdout']}")
                        print(f"Command: {error_info['command']}")
                    elif error_info['error_type'] == 'exception':
                        print(f"Error: {error_info['error_class']}: {error_info['error_message']}")
                
                print("-" * 40)
            
            # Save failed files to a log file
            log_file = "replace-all-failed.log"
            try:
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.write(f"Replace-all failed files log - {len(failed_files)} failures\n")
                    f.write("=" * 80 + "\n\n")
                    for failed in failed_files:
                        f.write(f"Local: {failed['local_path']}\n")
                        f.write(f"ISO:   {failed['iso_path']}\n")
                        f.write(f"Rel:   {failed['relative_path']}\n")
                        
                        # Write error details to log
                        error_info = failed['error_info']
                        if error_info:
                            if error_info['error_type'] == 'subprocess_error':
                                f.write(f"Error: Subprocess failed (exit code: {error_info['exit_code']})\n")
                                if error_info['stderr']:
                                    f.write(f"STDERR: {error_info['stderr']}\n")
                                if error_info['stdout']:
                                    f.write(f"STDOUT: {error_info['stdout']}\n")
                                f.write(f"Command: {error_info['command']}\n")
                            elif error_info['error_type'] == 'exception':
                                f.write(f"Error: {error_info['error_class']}: {error_info['error_message']}\n")
                        
                        f.write("-" * 40 + "\n")
                print(f"\nFailed files list saved to: {log_file}")
            except Exception as e:
                print(f"\nWarning: Could not save failed files log: {e}")
        
        return failed_count == 0

def main():
    """Main entry point"""
    print("REPLACE-ALL - Python version")
    print("Bulk file replacement tool for PSP UMD ISO images\n")
    
    try:
        # Create replacer instance
        replacer = BulkReplacer(
            iso_path=ISO_PATH,
            umd_script=UMD_REPLACE_SCRIPT,
            usrdir_path=USRDIR_PATH,
            file_globs=FILE_GLOBS
        )
        
        # Run the replacement process
        success = replacer.replace_all()
        
        if success:
            print("\nAll files replaced successfully!")
            sys.exit(0)
        else:
            print("\nSome files failed to replace.")
            sys.exit(1)
            
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    except NotADirectoryError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
