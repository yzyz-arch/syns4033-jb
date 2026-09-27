---
name: python-bleeding-edge-compatibility
description: "Fix library import errors on bleeding-edge Python 3.13+."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [python, compatibility, debugging, version-issues, sqlalchemy]
    related_skills: [systematic-debugging]
---

# Python Bleeding-Edge Version Compatibility

## Overview

Bleeding-edge Python versions (3.13+, alphas, betas) often have compatibility issues with popular libraries. Many libraries lag behind by 6-12 months.

**This skill covers diagnosing and fixing compatibility issues without downgrading Python.**

## When to Use

Use when:
- User has Python 3.13, 3.14, or newer alpha/beta versions
- Import errors occur with well-known libraries (SQLAlchemy, numpy, pandas, etc.)
- Errors reference internal library symbols, enums, or language features
- Libraries work on Python 3.11/3.12 but fail on newer versions

**Signals:**
- `ImportError` or `ModuleNotFoundError` after successful `pip install`
- Errors in library internals (not user code)
- Stack traces ending in `<library>/internals/*.py`
- Errors mentioning `FastIntFlag`, `IntEnum`, `symbol()`, metaclass issues

## Diagnostic Pattern

### Step 1: Confirm Python Version

```bash
python --version
# If 3.13+, especially 3.14+ (alpha/beta), suspect compatibility issues
```

### Step 2: Identify the Failing Library

Look at the import traceback:
```python
File ".../sqlalchemy/util/langhelpers.py", line 1663
    sym = symbol(k, canonical=v)
          ^^^^^^^^^^^^^^^^^^^^^
```

The library path (here `sqlalchemy`) is the culprit.

### Step 3: Check if async/await is involved

Async libraries have MORE compatibility issues with bleeding-edge Python because:
- async/await internals change more frequently
- Event loop changes break async libraries
- Type hint changes affect async codebases more

**Quick check:**
```bash
grep -r "async def\|await " <library_code_triggering_error>
```

If the library uses async extensively, try sync alternatives first.

## Common Patterns and Fixes

### Pattern 1: SQLAlchemy Async → Sync

**Symptom:**
```python
File ".../sqlalchemy/util/langhelpers.py", line 1663
    sym = symbol(k, canonical=v)
File ".../sqlalchemy/sql/compiler.py", line 615
```

**Root cause:** SQLAlchemy async engine incompatible with Python 3.14+

**Fix:** Convert to sync SQLAlchemy

**Before (async):**
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

async_engine = create_async_engine("sqlite+aiosqlite:///db.db")
AsyncSessionLocal = async_sessionmaker(async_engine, class_=AsyncSession)

async def get_data():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Model))
        return result.scalars().all()
```

**After (sync):**
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager

engine = create_engine("sqlite:///db.db")
SessionLocal = sessionmaker(engine)

@contextmanager
def get_db():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()

def get_data():
    with get_db() as session:
        result = session.execute(select(Model))
        return result.scalars().all()
```

**Requirements.txt changes:**
```diff
- sqlalchemy==2.0.30
- aiosqlite==0.19.0
+ sqlalchemy==2.0.36  # or latest
```

### Pattern 2: Try Pre-release Versions

For libraries actively maintained, pre-release versions may have Python 3.14 support:

```bash
pip install --pre --upgrade <library>
```

**When to try:**
- Library is actively maintained (commits in last 3 months)
- Official docs mention Python 3.13+ support
- GitHub issues show 3.14 compatibility PRs merged

**When to skip:**
- Library hasn't been updated in 6+ months
- No open issues about Python 3.14
- Better to use stable alternatives

### Pattern 3: Downgrade Python (Last Resort)

If no workaround exists and project needs the library:

**Recommended stable versions:**
- Python 3.12.x - Most compatible
- Python 3.11.x - Very stable, wide support

**Setup:**
```bash
# Using pyenv (recommended)
pyenv install 3.12.7
pyenv local 3.12.7

# Or create venv with specific version
python3.12 -m venv venv312
source venv312/bin/activate  # Linux/Mac
venv312\Scripts\activate     # Windows
```

## Decision Tree

```
Import error on Python 3.13+?
  │
  ├─ Is it in library internals? (not your code)
  │   │
  │   ├─ Is it an async library?
  │   │   │
  │   │   ├─ YES → Try sync alternative first
  │   │   │
  │   │   └─ NO → Continue
  │   │
  │   ├─ Try pre-release: pip install --pre --upgrade <lib>
  │   │   │
  │   │   ├─ Works? → Done
  │   │   │
  │   │   └─ Still fails? → Continue
  │   │
  │   ├─ Check for sync alternative
  │   │   │
  │   │   ├─ Exists? → Convert code
  │   │   │
  │   │   └─ No alternative? → Continue
  │   │
  │   └─ Downgrade to Python 3.12.x
  │
  └─ Is it in your code?
      └─ Use systematic-debugging skill
```

## Conversion Checklist: Async → Sync

When converting async code to sync:

- [ ] Remove all `async def` → `def`
- [ ] Remove all `await` keywords
- [ ] Change `AsyncSession` → `Session`
- [ ] Change `create_async_engine` → `create_engine`
- [ ] Change `async_sessionmaker` → `sessionmaker`
- [ ] Update database URL (remove `+aiosqlite`, `+asyncpg` suffixes)
- [ ] Replace `async with` → `with` (or `@contextmanager`)
- [ ] Update imports (remove `.asyncio` imports)
- [ ] Remove async-specific dependencies (aiosqlite, asyncpg, etc.)
- [ ] Update all calling code to remove `await`
- [ ] Test that database operations still work

## Verification

After any compatibility fix:

```bash
# Syntax check
python -m py_compile your_file.py

# Import check (should not raise)
python -c "import your_module"

# Run tests
pytest tests/
```

## References

See `references/python-314-sqlalchemy-async-error.md` for detailed error transcripts from real sessions.

## Pitfalls

### Critical: Clear Python Cache After Conversion

**Symptom:**
```python
ImportError: cannot import name 'AsyncSessionLocal' from 'database'
Did you mean: 'SessionLocal'?
```

Even after removing `AsyncSessionLocal` from source code, Python's `__pycache__` holds stale bytecode.

**Fix (try in order of severity):**

**1. Basic cache clear:**
```bash
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null
```

**2. If still fails: Use `python -B` flag**

The `-B` flag forces Python to ignore ALL bytecode files:
```bash
python -B your_script.py
```

This bypasses the cache completely, loading only source `.py` files.

**3. If STILL fails: Restart terminal/Python process**

Sometimes the Python interpreter process itself has cached imports in memory. Close all terminals running Python, open a NEW terminal, then run:
```bash
# Clear cache in fresh terminal
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
python -B your_script.py
```

**Why cache persists:**
- `__pycache__` can have nested directories
- Venv site-packages may cache imports
- Python process holds imports in memory across multiple runs
- On Windows, file locks can prevent deletion

**Always clear cache after async→sync conversion!** For stubborn cases, `python -B` + terminal restart is the nuclear option.

### Critical: 'NoneType' object can't be awaited

**Symptom:**
```
CRITICAL | __main__ - Fatal error: 'NoneType' object can't be awaited
```

**Root cause:** Awaiting a sync function that returns None (or implicitly returns None).

**Common patterns:**
```python
# WRONG: awaiting sync function
async def post_init():
    await init_db()  # init_db is sync, returns None
    # Python tries to await None → error

# WRONG: awaiting sync method
db_user = await UserService.get_user()  # if get_user is sync

# WRONG: awaiting sync database operation
await db.commit()  # if using sync Session
```

**Fix:** Remove `await` from sync operations:
```python
# RIGHT
async def post_init():
    init_db()  # no await

db_user = UserService.get_user()  # no await

db.commit()  # no await
```

**Diagnostic:**
1. Find the line causing crash (usually in traceback before "Fatal error")
2. Check if function being awaited is actually async:
   ```python
   # Sync function (no await needed):
   def func(): ...
   
   # Async function (needs await):
   async def func(): ...
   ```
3. Remove await if function is sync

### Critical: Mixing Sync Operations in Async Callbacks

**Symptom:** Bot/server starts, logs "Initializing...", then crashes with 'NoneType' error.

**Root cause:** Calling blocking sync operations (like `init_db()`) inside async initialization callbacks.

**Example problem:**
```python
# Telegram bot, FastAPI, etc.
async def post_init(application):
    logger.info("Initializing...")
    init_db()  # BLOCKS async event loop!
    # Crash happens here or shortly after
```

**Fix:** Don't call sync init functions in async callbacks. Either:

**Option 1:** Run init BEFORE creating async application
```python
def main():
    init_db()  # Run BEFORE async app
    
    app = Application.builder().token(...).build()
    app.run_polling()
```

**Option 2:** Use async wrapper if init must be in callback
```python
import asyncio

async def post_init(application):
    await asyncio.to_thread(init_db)  # Run in thread pool
```

**Option 3:** Make init minimal (most common for bots)
```python
# Database should already be initialized (via separate script)
# Callback just logs ready
async def post_init(application):
    logger.info("✅ Bot ready!")  # No database calls
```

**DON'T:**
- Assume the error is in your code when it's in library internals
- Try to monkey-patch library internals
- Install from random GitHub forks
- Use `--pre` blindly without checking if maintainers are active
- Forget to clear `__pycache__` after async→sync conversion

**DO:**
- Check Python version FIRST when seeing import errors
- Look for sync alternatives before trying pre-releases
- Clear Python cache after any async→sync conversion
- Test thoroughly after conversion
- Document which Python version the project needs
- Search for ALL `await` statements and verify each one is on an async function

## When This Skill Doesn't Apply

**NOT for:**
- Syntax errors in your own code
- Missing dependencies (package not installed)
- Virtual environment issues
- Import errors that work on same Python version elsewhere (→ environment problem)
- Runtime errors after successful imports (→ different issue)
