#!/usr/bin/env python3
"""
Convert Mermaid diagram files (.mmd) to SVG using Mermaid.ink API

Usage:
    python convert_mermaid_to_svg.py
    
This will convert all .mmd files in the current directory to .svg files.
"""

import base64
import pathlib
import urllib.request
import urllib.parse
import sys


def mermaid_to_svg(mermaid_code: str) -> bytes:
    """
    Convert Mermaid code to SVG using the Mermaid.ink service.
    
    Args:
        mermaid_code: Mermaid diagram code
        
    Returns:
        SVG content as bytes
    """
    # Encode mermaid code to base64
    encoded = base64.b64encode(mermaid_code.encode('utf-8')).decode('ascii')
    
    # Construct URL
    url = f"https://mermaid.ink/svg/{encoded}"
    
    try:
        # Fetch SVG from service
        with urllib.request.urlopen(url, timeout=30) as response:
            if response.status == 200:
                return response.read()
            else:
                raise Exception(f"HTTP {response.status}: {response.reason}")
    except urllib.error.URLError as e:
        raise Exception(f"Failed to fetch SVG: {e}")


def convert_file(mmd_file: pathlib.Path) -> pathlib.Path:
    """
    Convert a single .mmd file to .svg
    
    Args:
        mmd_file: Path to .mmd file
        
    Returns:
        Path to generated .svg file
    """
    print(f"Converting {mmd_file.name}...", end=" ")
    
    # Read mermaid code
    mermaid_code = mmd_file.read_text(encoding='utf-8')
    
    # Convert to SVG
    try:
        svg_content = mermaid_to_svg(mermaid_code)
    except Exception as e:
        print(f"❌ FAILED")
        print(f"  Error: {e}")
        return None
    
    # Write SVG file
    svg_file = mmd_file.with_suffix('.svg')
    svg_file.write_bytes(svg_content)
    
    print(f"✅ SUCCESS → {svg_file.name}")
    return svg_file


def main():
    """Convert all .mmd files in the current directory to .svg"""
    
    # Get current directory
    current_dir = pathlib.Path(__file__).parent
    
    # Find all .mmd files
    mmd_files = list(current_dir.glob('*.mmd'))
    
    if not mmd_files:
        print("No .mmd files found in current directory")
        return 1
    
    print(f"Found {len(mmd_files)} mermaid diagram(s)")
    print("-" * 60)
    
    # Convert each file
    success_count = 0
    failed_count = 0
    
    for mmd_file in mmd_files:
        result = convert_file(mmd_file)
        if result:
            success_count += 1
        else:
            failed_count += 1
    
    # Print summary
    print("-" * 60)
    print(f"Conversion complete:")
    print(f"  ✅ Success: {success_count}")
    print(f"  ❌ Failed: {failed_count}")
    
    if failed_count > 0:
        print("\n⚠️  Some conversions failed. Check the errors above.")
        return 1
    
    print("\n🎉 All diagrams converted successfully!")
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n❌ Conversion cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)

