---
name: security-toolkit-delivery
description: "Build clean ZIP archives for security toolkits — filter legacy paths, sanitize naming, and deliver branded packages with zero repository references."
version: 1.0.0
author: IKONA Security Team
category: security
---

# Build Clean Security ZIP Archives

## When to Use This Skill

- Packaging exploit scripts, payloads, and tools for delivery
- Creating "IKONA" branded archives from GitHub repos or internal folders
- Removing legacy names (`cybermes`, `hack-skills`, `elementalsouls`) before shipping
- Ensuring 100% path sanitization before distribution

## Problem Statement

Security repos often have nested paths that break when shipped:

```
❌ Legacy paths in archive:
skills/cybermes/hacktricks/src/pentesting-web/sql-injection/stacked-queries.md
skills/cybermes/clause-bughunter/exercises/401-403/README.md
skills/security/web-exploit-test/scripts/__pycache__/sqli.py
```

These paths reveal:
- Repository origins (leaks attribution)
- Internal structure you may not want exposed
- Mixed naming conventions ("cybermes", "hack-skills", "IKONA")

## Solution: Filter-Based Path Sanitization

### Step 1: Define Skip Patterns

```python
SKIP_PATTERNS = [
    'hacktricks/src/',       # Deep nested sources
    'hacktricks\\src\\',     # Windows-style
    'pentesting-web/',       # Category subfolders
    'node_modules/',         # Dependencies
    '__pycache__/',          # Python cache
    '.git/',                 # Git history
    'CLAUDE.md',            # Agent configs
    'AGENTS.md',            # Multi-agent routers
]
```

### Step 2: Collect Files With Filtering

```python
import os, zipfile

def collect_clean(base_path, skip_patterns):
    """Collect all files, filtering out bad paths."""
    files = []
    
    for root, dirs, filenames in os.walk(base_path):
        # Remove directories we don't want to traverse
        dirs[:] = [d for d in dirs if not any(p in d for p in skip_patterns)]
        
        if '__pycache__' in root:
            continue
        
        for fname in filenames:
            full_path = os.path.join(root, fname)
            
            # Calculate relative path
            rel_path = os.path.relpath(full_path, base_path)
            
            # Skip if contains any bad pattern
            if any(pattern in rel_path for pattern in skip_patterns):
                continue
            
            # Only include known file types (optional filter)
            ext = os.path.splitext(fname)[1].lower()
            if ext and len(ext) <= 5:
                files.append((full_path, rel_path))
    
    return files

def build_ikonazip(base_path, output_zip, archive_prefix="IKONA"):
    """Build clean IKONA-branded archive."""
    skip_patterns = [
        'hacktricks/src/', 'hacktricks\\src\\', 
        'node_modules/', '__pycache__', '.git'
    ]
    
    files = collect_clean(base_path, skip_patterns)
    
    print(f"\nBuilding {archive_prefix} archive...")
    print(f"Base path: {base_path}")
    print(f"Total files found: {len(files)}")
    
    # Create ZIP
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for full_path, rel_path in files:
            arc_name = f"{archive_prefix}/{rel_path}"
            zf.write(full_path, arc_name)
    
    # Verify
    with zipfile.ZipFile(output_zip, 'r') as zf:
        names = zf.namelist()
        bad_paths = [n for n in names if any(p in n for p in ['hacktricks/src', 'node_modules', '__pycache__'])]
        
        print(f"\nArchive built: {output_zip}")
        print(f"Total entries: {len(names)}")
        print(f"Legacy paths: {len(bad_paths)}")  # Must be 0
        
        if bad_paths:
            print("\n⚠️  Legacy paths found:")
            for bp in bad_paths[:5]:
                print(f"  - {bp}")
        else:
            print("✓ Clean! All paths use IKONA prefix")

# Usage
build_ikonazip(
    r'C:\Users\SERVER\AppData\Local\hermes\skills\cybermes',
    r'C:\Users\SERVER\Desktop\IKONA FULL v3.zip',
    "IKONA"
)
```

### Step 3: Extract Python-Only Archive (Optional)

For script-only delivery:

```python
def extract_py_only(base_path, output_zip, archive_prefix="IKONA_EXPLOIT"):
    """Extract only .py files for compact package."""
    files = []
    
    for root, dirs, filenames in os.walk(base_path):
        if '__pycache__' in root:
            continue
        
        for fname in filenames:
            if not fname.endswith('.py'):
                continue
            
            full_path = os.path.join(root, fname)
            rel_path = os.path.relpath(full_path, base_path)
            
            # Still skip bad paths
            if any(p in rel_path for p in ['hacktricks/src', 'node_modules']):
                continue
            
            files.append((full_path, rel_path))
    
    print(f"\nBuilding {archive_prefix}...")
    print(f".py files only: {len(files)}")
    
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for full_path, rel_path in files:
            # Normalize path: remove skill folder, just keep script name
            parts = rel_path.split(os.sep)
            # e.g. "exploit_scripts/sqli_exploit.py" → "IKONA_EXPLOIT/sqli_exploit.py"
            normalized = f"{archive_prefix}/{'/'.join(parts[-2:])}"
            zf.write(full_path, normalized)
    
    print(f"✓ Built: {output_zip}")
```

## Verification Commands

After building:

```python
import zipfile

with zipfile.ZipFile('IKONA_FULL_v3.zip', 'r') as zf:
    names = zf.namelist()
    
    print(f"\nArchive Statistics:")
    print(f"  Total files: {len(names)}")
    
    # Count by extension
    extensions = {}
    for n in names:
        ext = os.path.splitext(n)[1].lower()
        extensions[ext] = extensions.get(ext, 0) + 1
    
    print(f"\nBy extension:")
    for ext, count in sorted(extensions.items(), key=lambda x: -x[1])[:10]:
        print(f"  {ext or '(no ext)':15} {count:6,}")
    
    # Check for legacy patterns
    bad = [n for n in names if any(p in n.lower() for p in ['hacktricks/src', 'cybermes/', 'hack-skills/', 'elementalsouls', 'claude-bughunter'])]
    print(f"\nLegacy references: {len(bad)}")  # Should be 0
    
    # Show sample paths
    print(f"\nSample paths (first 10):")
    for n in names[:10]:
        print(f"  • {n}")
```

## Expected Output

```
Building IKONA archive...
Base path: C:\Users\SERVER\AppData\Local\hermes\skills\cybermes
Total files found: 3269

Archive built: IKONA FULL v3.zip
Total entries: 3269
Legacy paths: 0
✓ Clean! All paths use IKONA prefix
```

## Pitfalls

1. **Forgotten subdirectories**: Always check `dirs[:]` modification during walk to prevent traversal into unwanted folders
2. **Case sensitivity**: Skip patterns should handle both `HackTricks/` and `hacktricks/` — normalize to lowercase when checking
3. **Symlinks**: On Linux, follow symlinks can create duplicate entries. Add `os.path.islink()` check.
4. **Large files**: Payloads/images can blow up archive size. Use `.zip -9` for maximum compression.
5. **Windows paths**: When checking paths, use both `/` and `\` separators for cross-platform consistency.

## Integration with Delivery

Once verified clean:

```bash
# Deliver via Telegram
telegram-send "IKONA FULL v3.zip ready\nFiles: 3269\nLegacy paths: 0\nChecksum: $(sha256sum IKONA_FULL_v3.zip | cut -d' ' -f1)"
```

Always include checksum so recipient can verify integrity.