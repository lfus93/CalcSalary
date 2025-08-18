"""
PyInstaller build script for creating optimized .exe
This script creates a smaller executable by excluding unnecessary modules
"""
import PyInstaller.__main__
import sys
import os

def build_exe():
    """Build optimized executable"""
    
    # Define excluded modules to reduce size
    excluded_modules = [
        # Large modules not needed
        'matplotlib',
        'scipy',
        'numpy.random._examples',
        'numpy.tests',
        'pandas.tests',
        'pandas.io.formats.style',
        'pandas.plotting',
        'IPython',
        'jupyter',
        'notebook',
        'tornado',
        'zmq',
        'PIL',
        'Pillow',
        # Testing modules
        'pytest',
        'unittest',
        'doctest',
        # Development tools
        'pdb',
        'profile',
        'pstats',
        # Networking (not needed)
        'urllib3',
        'requests',
        'http.server',
        'socketserver',
        'xmlrpc',
        # Multiprocessing (not needed)
        'multiprocessing',
        'concurrent.futures',
        # Crypto (not needed)
        'cryptography',
        'ssl',
        # Compression (keep basic ones)
        'bz2',
        'lzma',
        # Database (not needed)
        'sqlite3',
        'dbm',
        # Email (not needed)
        'email',
        'smtplib',
        'poplib',
        'imaplib',
    ]
    
    # PyInstaller arguments
    args = [
        'main.py',                    # Main script
        '--name=PilotSalaryCalc',     # Executable name
        '--onefile',                  # Single file executable
        '--windowed',                 # No console window
        '--optimize=2',               # Maximum optimization
        '--strip',                    # Strip debug symbols
        '--clean',                    # Clean cache
        '--distpath=dist',            # Output directory
        '--workpath=build',           # Build directory
        # Add data files
        '--add-data=cord_airport.csv;.',
        # Icon (if available)
        # '--icon=icon.ico',
        # Exclude modules
        *[f'--exclude-module={module}' for module in excluded_modules],
        # Hidden imports (if needed)
        '--hidden-import=pandas._libs.tslibs.timedeltas',
        '--hidden-import=pandas._libs.tslibs.np_datetime',
        '--hidden-import=pandas._libs.tslibs.nattype',
        '--hidden-import=pandas._libs.reduction',
        # Collect submodules for our app
        '--collect-submodules=config',
        '--collect-submodules=models',
        '--collect-submodules=services',
        '--collect-submodules=utils',
    ]
    
    print(f"Building executable with PyInstaller...")
    print(f"Excluded modules: {len(excluded_modules)}")
    
    # Run PyInstaller
    PyInstaller.__main__.run(args)
    
    print("Build complete!")
    print("Executable location: dist/PilotSalaryCalc.exe")

if __name__ == "__main__":
    build_exe()