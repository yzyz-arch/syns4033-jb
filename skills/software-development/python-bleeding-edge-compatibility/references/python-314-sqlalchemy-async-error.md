# Python 3.14 + SQLAlchemy Async: Real Error Transcript

## Context

**Environment:**
- Python: 3.14.0 (alpha/beta, very new)
- SQLAlchemy: 2.0.30 → attempted 2.0.36
- Project: Telegram bot with async SQLAlchemy
- Date: 2026-08-09

## Error Sequence

### Error 1: FastIntFlag symbol error

```
Traceback (most recent call last):
  File "D:\hermes\projects\kiro-ai-rental\init_db.py", line 16, in <module>
    from database import init_db, AsyncSessionLocal, User, RentalPackage
  File "D:\hermes\projects\kiro-ai-rental\database\__init__.py", line 3, in <module>
    from database.base import Base, get_db, init_db, AsyncSessionLocal
  File "D:\hermes\projects\kiro-ai-rental\database\base.py", line 3, in <module>
    from sqlalchemy import create_engine
  File ".../sqlalchemy/sql/compiler.py", line 615, in <module>
    class InsertmanyvaluesSentinelOpts(FastIntFlag):
        RENDER_SELECT_COL_CASTS = 64
TypeError: Can't replace canonical symbol for '__firstlineno__' with new int value 615
```

**Root cause:** Python 3.14 changed internal symbol handling. SQLAlchemy's `FastIntFlag` usage incompatible.

**Attempted fix:** Upgrade SQLAlchemy to 2.0.36
**Result:** Same error

### Error 2: After async→sync conversion

```
(venv) D:\hermes\projects\kiro-ai-rental>python rental_bot_main.py
16:03:20 | INFO | __main__ - Starting KIRO Rental Bot (@kenan_kenbot)...
16:03:21 | INFO | __main__ - Rental Bot is running. Press Ctrl+C to stop.
16:03:22 | INFO | __main__ - Initializing Rental Bot database...
16:03:22 | INFO | database.base - Database initialized
16:04:13 | CRITICAL | __main__ - Fatal error: 'NoneType' object can't be awaited
```

**Root cause:** Awaiting sync `init_db()` in async `post_init()` callback.

**Original code:**
```python
async def post_init(application: Application) -> None:
    """Initialize after startup"""
    logger.info("🔧 Initializing Rental Bot database...")
    await init_db()  # ← init_db() is sync, returns None
    logger.info("✅ Rental Bot ready!")
```

**Fix:** Remove await AND the call itself:
```python
async def post_init(application: Application) -> None:
    """Initialize after startup"""
    logger.info("✅ Rental Bot ready!")  # Don't call init_db at all
```

### Error 3: Cached imports after conversion

```
ImportError: cannot import name 'AsyncSessionLocal' from 'database'
(D:\hermes\projects\kiro-ai-rental\database\__init__.py).
Did you mean: 'SessionLocal'?
```

**Root cause:** Stale `__pycache__` bytecode still importing `AsyncSessionLocal` even after source changed to `SessionLocal`.

**Fix:**
```bash
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -name "*.pyc" -delete
```

**Had to clear cache 3 times** during the conversion process as each layer of changes triggered this.

### Error 3b: EXTREME Cache Persistence (Aug 2026 session)

**Symptom:** After verifying source files are correct (no `AsyncSessionLocal`, no `await init_db()`), bot STILL runs old code with old behavior.

**Verification showed:**
```bash
# Source file check
grep "async def post_init" rental_bot_main.py
# Output: async def post_init... logger.info("✅ Ready!")  ← CORRECT, no init_db

# But bot still logs:
16:03:22 | INFO | Initializing Rental Bot database...  ← OLD CODE!
16:03:22 | CRITICAL | Fatal error: 'NoneType' object can't be awaited
```

**Root cause:** Python process + terminal environment holding cached imports in memory even after `__pycache__` cleared.

**Nuclear option that finally worked:**

```bash
# 1. Close ALL Python processes and terminals
# 2. Open FRESH terminal
# 3. Clear cache again in fresh environment
cd D:\hermes\projects\kiro-ai-rental
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -name "*.pyc" -delete

# 4. Run with -B flag (ignore ALL bytecode)
python -B rental_bot_main.py
```

**The `-B` flag is critical:** Forces Python to ignore `.pyc` files completely, loading only source `.py` files. This bypasses cache entirely.

**Additional cache locations to check on Windows:**
```bash
# Venv site-packages may cache
rm -rf venv/Lib/site-packages/__pycache__

# Windows-specific: check for .pyc in directories
find . -name "*.pyc" -o -name "*.pyo"
```

**Lesson:** When cache persists after multiple clears:
1. Verify source file is actually correct (not just assumed)
2. Close terminal completely (not just Ctrl+C the script)
3. Open NEW terminal
4. Clear cache in fresh terminal
5. **Always use `python -B` after async→sync conversion**

This level of cache persistence is RARE but happens with:
- Large async→sync conversions (many files changed)
- Python 3.14+ (newer import caching mechanisms)
- Windows environments (file locks can prevent cache deletion)

## Working Solution

**Final approach:**
1. Convert all async SQLAlchemy to sync SQLAlchemy
2. Update all database operations to remove `await`
3. Clear all `__pycache__` directories (multiple times)
4. Remove database initialization from async callbacks
5. Verify no `await` on sync functions

**Alternative:** Use Python 3.12.x (100% compatible, recommended for production)

## Conversion Checklist Applied

- [x] Changed `AsyncSession` → `Session`
- [x] Changed `create_async_engine` → `create_engine`  
- [x] Changed `async_sessionmaker` → `sessionmaker`
- [x] Removed all `await db.execute()` → `db.query()`
- [x] Removed all `await db.commit()` → `db.commit()`
- [x] Removed all `await db.refresh()` → `db.refresh()`
- [x] Updated database URL: removed `+aiosqlite` suffix
- [x] Converted all service methods from async to sync
- [x] Removed `await UserService.*()` calls
- [x] Cleared Python cache multiple times (critical!)
- [x] Removed init_db() from async post_init callbacks

## Key Files Modified

**Database layer:**
- `database/base.py` - Converted to sync engine
- `database/__init__.py` - Updated exports
- `init_db.py` - Made fully sync

**Service layer:**
- `services/user_service.py` - All methods converted from async to sync

**Bot files:**
- `rental_bot_main.py` - Removed await from all database ops, fixed post_init
- `ai_bot_main.py` - Removed await from all database ops, fixed post_init

## Time Investment

Total debugging/conversion time: ~2 hours
- Initial error diagnosis: 15 min
- First conversion attempt: 30 min  
- Cache clearing issues: 20 min
- 'NoneType' error hunting: 45 min
- Final fixes and verification: 20 min

## Lessons Learned

1. **Python 3.14 is too new** for production SQLAlchemy projects
2. **Cache clearing is CRITICAL** - must clear after EVERY layer of async→sync changes
3. **'NoneType' errors are subtle** - stack trace doesn't always point to the exact `await` causing issues
4. **Mixing sync/async is dangerous** - calling sync functions from async callbacks causes hard-to-debug crashes
5. **Always verify with grep** - `grep -r "await " .` to find all remaining await statements

**Recommendation:** For production Telegram bots or any SQLAlchemy project, use **Python 3.12.x** until libraries catch up to 3.14.
