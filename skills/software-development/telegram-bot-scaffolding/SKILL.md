---
name: telegram-bot-scaffolding
description: Create production Telegram bot project structures.
author: Hermes Curator
license: MIT
triggers:
  - Creating a Telegram bot project from scratch
  - Setting up a bot with python-telegram-bot library
  - Need complete bot structure (not just a single script)
  - User asks for rental/marketplace/service bot structure
tags: [telegram, bot, python, scaffolding, architecture]
version: 1.0.0
metadata:
  hermes:
    tags: [project-scaffolding, telegram-bot, clean-architecture]
    related_skills:
      - hermes-agent-skill-authoring
      - github-pr-workflow
---

# Telegram Bot Project Scaffolding

## Overview

Create complete, production-ready Telegram bot projects with clean 3-layer architecture, comprehensive documentation, testing, and DevOps tooling. Goes beyond simple bot tutorials to deliver enterprise-grade structure.

## When to Use

- User needs a complete bot project (not just examples)
- Building service bots (rental, marketplace, booking, etc.)
- Need clean architecture from the start
- Want tests, Docker, CI/CD ready
- Project will grow beyond a single script

## Architecture Pattern

### 3-Layer Clean Architecture

```
bot/          → Telegram interface layer (handlers, keyboards, middlewares)
services/     → Business logic layer
database/     → Data layer (models, migrations)
```

**Key principle**: Handlers are thin - they parse Telegram updates, call services, format responses. Services contain all business logic and are independently testable.

## File Structure Template

### Core Structure
```
project-name/
├── bot/
│   ├── handlers/           # Command & callback handlers
│   │   ├── start_handler.py
│   │   ├── main_feature_handler.py
│   │   └── admin_handler.py
│   ├── keyboards/          # UI layouts
│   │   ├── inline_keyboards.py
│   │   └── main_keyboard.py
│   ├── middlewares/        # Cross-cutting concerns
│   │   ├── auth.py
│   │   └── logging.py
│   └── utils/              # Helpers
│       └── helpers.py
│
├── database/
│   ├── models/             # SQLAlchemy models
│   ├── migrations/         # Alembic (or README for future)
│   └── base.py             # Engine, session config
│
├── services/               # Business logic
│   ├── user_service.py
│   └── feature_service.py
│
├── tests/                  # Test suite
│   ├── conftest.py         # Fixtures
│   └── test_*.py
│
├── scripts/                # Utilities
│   ├── init_db.py
│   └── backup_db.py
│
├── main.py                 # Entry point
├── config.py               # Settings (pydantic-settings)
├── requirements.txt
└── setup.py                # Quick setup script
```

### Documentation Structure

Create **tiered documentation** for different audiences:

1. **START_HERE.md** or **FINAL_REPORT.md** - Visual, quick-scan guide for first run
2. **QUICKSTART.md** - 5-minute setup for developers
3. **README.md** - Project overview, features, tech stack
4. **DEPLOYMENT.md** - Production deployment guide
5. **docs/API.md** - API reference, models, commands
6. **docs/README.md** - Developer deep-dive, architecture diagrams
7. **CONTRIBUTING.md** - Contribution guidelines
8. **SECURITY.md** - Security policy
9. **CHANGELOG.md** - Version history

### DevOps Files

Include from the start:
- `Dockerfile` + `docker-compose.yml`
- `.github/workflows/ci-cd.yml`
- `deployment/systemd-service-file`
- `Makefile` with dev commands
- `.editorconfig`, `.flake8`, `pyproject.toml`

## Implementation Steps

### 1. Create Directory Structure First

```bash
mkdir -p bot/{handlers,keyboards,middlewares,utils}
mkdir -p database/{models,migrations}
mkdir -p services tests scripts docs deployment
mkdir -p static/{images,uploads} logs
```

Use `terminal` to create directories, not individual `write_file` calls.

### 2. Core Files in Order

**Priority 1 - Foundation:**
1. `config.py` (pydantic-settings)
2. `database/base.py` (async engine setup)
3. `database/models/*.py` (all models)
4. `.env.example` (template)

**Priority 2 - Bot Layer:**
5. `bot/handlers/*.py` (start with start_handler)
6. `bot/keyboards/*.py`
7. `bot/middlewares/*.py`
8. `bot/utils/helpers.py`

**Priority 3 - Business Logic:**
9. `services/*.py` (one per major feature)

**Priority 4 - Infrastructure:**
10. `main.py` (entry point with all wiring)
11. `scripts/init_db.py`
12. `tests/conftest.py` + test files

**Priority 5 - Documentation & Config:**
13. All markdown files
14. Docker files, CI/CD, Makefile
15. `setup.py` (quick setup script)

### 3. python-telegram-bot Patterns

**Handler registration in main.py:**
```python
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

application = Application.builder().token(BOT_TOKEN).build()

# Commands
application.add_handler(CommandHandler("start", start_handler.start))
application.add_handler(CommandHandler("help", help_handler.help_command))

# Callbacks with patterns
application.add_handler(CallbackQueryHandler(
    item_handler.item_detail, 
    pattern="^item_"
))

# Error handler
application.add_error_handler(error_handler)

# Run
application.run_polling(allowed_updates=Update.ALL_TYPES)
```

**Handler structure:**
```python
async def command_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler docstring"""
    user = update.effective_user
    
    # Call service layer (don't put business logic here)
    result, error = await SomeService.do_something(db, user.id, ...)
    
    if error:
        await update.message.reply_text(f"❌ {error}")
        return
    
    # Format response
    await update.message.reply_text(
        format_response(result),
        parse_mode="Markdown",
        reply_markup=get_keyboard()
    )
```

**Callback query handling:**
```python
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()  # ALWAYS answer first
    
    # Extract data
    item_id = query.data.replace("prefix_", "")
    
    # Process
    result = await service_call(item_id)
    
    # Update message
    await query.edit_message_text(
        new_text,
        reply_markup=new_keyboard
    )
```

### 4. Async SQLAlchemy Setup

**database/base.py:**
```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Convert sqlite:/// to sqlite+aiosqlite:///
async_db_url = DATABASE_URL.replace("sqlite://", "sqlite+aiosqlite://")

async_engine = create_async_engine(async_db_url, echo=DEBUG)
AsyncSessionLocal = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

**Service layer pattern:**
```python
class UserService:
    @staticmethod
    async def get_or_create_user(db: AsyncSession, telegram_id: int, ...) -> User:
        result = await db.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        
        if not user:
            user = User(telegram_id=telegram_id, ...)
            db.add(user)
            await db.commit()
            await db.refresh(user)
        
        return user
```

### 5. Test Structure

**conftest.py:**
```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture(scope="function")
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = async_sessionmaker(engine, class_=AsyncSession)
    async with async_session() as session:
        yield session
    
    await engine.dispose()
```

### 6. Quick Setup Script

Create `setup.py` that:
1. Checks Python version (3.11+)
2. Warns if not in venv
3. Installs requirements
4. Creates .env from template
5. Initializes database
6. Creates directories
7. Prints next steps

## Pitfalls

### 1. Inline Keyboards vs Reply Keyboards

**Problem**: Using wrong keyboard type or mixing incorrectly.

**Solution**:
- **Reply keyboards** (ReplyKeyboardMarkup): Persistent buttons that replace keyboard. Use for main navigation.
- **Inline keyboards** (InlineKeyboardMarkup): Attached to messages with callback_data. Use for actions on specific content.

```python
# Reply keyboard (main menu)
from telegram import ReplyKeyboardMarkup, KeyboardButton
keyboard = [[KeyboardButton("📦 Catalog"), KeyboardButton("👤 Profile")]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Inline keyboard (actions)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
keyboard = [[InlineKeyboardButton("Book", callback_data=f"book_{item_id}")]]
reply_markup = InlineKeyboardMarkup(keyboard)
```

### 2. Forgetting to Answer Callback Queries

**Problem**: Telegram shows "loading" forever if you don't answer.

**Solution**: ALWAYS call `await query.answer()` first:
```python
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # ← REQUIRED
    # ... rest of handler
```

### 3. Business Logic in Handlers

**Problem**: Putting validation, calculations, database logic in handlers makes them untestable and violates clean architecture.

**Solution**: Handlers should only:
- Parse Telegram input
- Call service layer
- Format responses

Move ALL business logic to services/.

### 4. Blocking Database Operations

**Problem**: Using sync SQLAlchemy with async bot causes blocking.

**Solution**: Use SQLAlchemy async throughout:
- `create_async_engine()`
- `AsyncSession`
- `await db.execute()`
- `await db.commit()`

### 5. Not Handling Long Operations

**Problem**: Commands timing out on long operations.

**Solution**: 
- Send "processing" message first
- Use `await context.bot.send_chat_action(chat_id, "typing")`
- For very long tasks, use background jobs

### 6. Missing Error Handlers

**Problem**: Uncaught exceptions crash the bot.

**Solution**: Add global error handler:
```python
async def error_handler(update: object, context) -> None:
    logger.error(f"Exception: {context.error}")
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("⚠️ Error occurred")

application.add_error_handler(error_handler)
```

### 7. Environment Variable Handling

**Problem**: Forgetting to create .env, or committing .env to git.

**Solution**:
- Always create `.env.example` with placeholders
- Add `.env` to `.gitignore`
- Use pydantic-settings for validation
- `setup.py` should auto-create .env from template

### 8. Markdown Parse Errors with @ Symbols

**Problem**: Using `@username` in Markdown messages causes `BadRequest: Can't parse entities: can't find end of the entity starting at byte offset X`.

**Root cause**: Telegram Markdown parser treats `@` as the start of a user mention entity. If it's just plain text (not a real mention), parsing fails.

**Solution**: Escape the `@` symbol with backslash:

```python
# WRONG - causes parse error
text = "Chat with @my_bot for help"
await message.reply_text(text, parse_mode="Markdown")
# ❌ BadRequest: Can't parse entities

# RIGHT - escape the @ symbol
text = r"Chat with @my\_bot for help"  # Note: raw string r""
await message.reply_text(text, parse_mode="Markdown")
# ✅ Works
```

**Important:** Use **raw strings** (`r"""`) to avoid Python's `SyntaxWarning: invalid escape sequence`:

```python
# WRONG - causes Python SyntaxWarning
text = "Message @bot\_name here"
# Warning: "\_ " is an invalid escape sequence

# RIGHT - use raw string
text = r"Message @bot\_name here"
# ✅ No warning, Telegram parses correctly
```

**Alternative solutions:**
1. **Remove Markdown parsing** for that message: `parse_mode=None`
2. **Use MarkdownV2** (requires different escaping rules)
3. **Use HTML parse mode** instead: `parse_mode="HTML"` with `<b>`, `<i>`, etc.

**Common Markdown special characters that need escaping:**
- `@` for usernames/mentions
- `_` for underscores (conflicts with italics)
- `*` for asterisks (conflicts with bold)
- `[` and `]` for links
- `` ` `` for code blocks

**Quick test:** If you see parse errors with "can't find end of entity", check for unescaped special characters in your message text.

## Verification

After creation, verify structure:

```bash
# Syntax check (should pass even without dependencies)
find . -name "*.py" -exec python -m py_compile {} \;

# File count
find . -type f | wc -l

# Python modules
find . -name "*.py" | wc -l
```

Expected blockers AFTER creation:
- Import errors (dependencies not installed) - EXPECTED
- Missing BOT_TOKEN - EXPECTED

These are setup state, not project issues. Document clearly in setup guide.

## Documentation Best Practices

### Visual Hierarchy

Use box drawing and clear sections:
```markdown
╔══════════════════════════════════════╗
║  PROJECT CREATION COMPLETE!          ║
╚══════════════════════════════════════╝

📊 STATISTICS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Files: 76
  Python: 43
```

### Multiple Entry Points

Different users need different starting points:
- Beginners → START_HERE.md (visual, step-by-step)
- Experienced → QUICKSTART.md (commands only)
- DevOps → DEPLOYMENT.md
- Contributors → CONTRIBUTING.md

### Concrete Examples

Always include:
- Exact commands to run
- Expected output
- What to edit (with examples)
- How to verify it worked

## Related Patterns

- For skill authoring: see `hermes-agent-skill-authoring`
- For general scaffolding: this skill focuses on Telegram bots specifically
- For API-only services: different pattern (no bot handlers, use FastAPI instead)
- **Payment proof approval flow**: see `references/payment-proof-approval-flow.md` for owner-review payment patterns with image verification
- **Windows bot automation**: see `references/windows-batch-bot-automation.md` for .bat file startup scripts

## Tool Usage Notes

- Create directories with `terminal mkdir -p` (faster than write_file for empty dirs)
- Use `.gitkeep` files for empty tracked directories
- Batch parallel writes when possible
- Create files in logical dependency order (config → models → services → handlers → main)
- Verify syntax with `python -m py_compile` after creation
