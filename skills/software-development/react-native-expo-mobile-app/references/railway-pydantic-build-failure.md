# Railway Python Deployment Failures: pydantic-core Compilation

## Problem

Railway deployments fail when trying to build Python FastAPI projects with recent Pydantic versions (2.x). The build crashes during `pydantic-core` wheel compilation with errors like:

```
Building wheel for pydantic-core (pyproject.toml): started
✗ Build failed
```

This happens even with minimal `requirements.txt` files.

## Root Cause

Railway's Python build environment has issues compiling Rust-based Python packages (pydantic v2 uses Rust for pydantic-core). The compilation requires:
- Rust compiler
- Sufficient build resources
- Compatible system libraries

Railway's build containers often lack these or time out during compilation.

## Solution: Use Pydantic v1 or Prebuilt Wheels

### Option 1: Downgrade to Pydantic v1 (RECOMMENDED)

**requirements.txt:**
```txt
fastapi==0.100.0
uvicorn==0.23.0
pydantic==1.10.12
python-multipart==0.0.6
aiohttp==3.8.5
beautifulsoup4==4.12.2
lxml==4.9.3
httpx==0.24.1
```

**Why this works:**
- Pydantic 1.x is pure Python (no Rust compilation)
- FastAPI 0.100.0 is compatible with Pydantic 1.x
- All packages have prebuilt wheels

### Option 2: Use Alternative Platform

Railway is particularly problematic for Python projects with compiled dependencies. Better alternatives:

**Render.com (RECOMMENDED for Python/FastAPI):**
```bash
# More reliable Python build environment
# Better handling of compiled dependencies
# Free tier available
```

**Vercel (Serverless):**
```bash
# Serverless Python functions
# No long-running compilation
# Good for API endpoints
```

**Ngrok (Local Development/Testing):**
```bash
# Run locally, expose via ngrok
# No cloud build issues
# Fastest for development
```

## Attempted Fixes That Don't Work

**❌ Using newer Pydantic versions:**
```txt
pydantic==2.5.0  # Still fails
pydantic==2.5.3  # Still fails
```

**❌ Removing optional extras:**
```txt
pydantic[email]==2.5.0  # Still fails without [email]
```

**❌ Adding build dependencies to requirements.txt:**
- Railway doesn't support apt-get in requirements.txt
- Cannot install Rust compiler this way

**❌ Using --no-binary flag:**
- Forces source build (even slower)
- Still fails on Railway

## Migration Path: Railway → Render

If you hit this on Railway, migrate to Render:

1. Go to https://render.com
2. Sign up (free)
3. New Web Service
4. Build command: `pip install -r requirements.txt`
5. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Deploy

**Works with both Pydantic 1.x and 2.x.**

## Alternative: Ngrok for Quick Testing

Instead of fighting cloud platforms:

```bash
# Start backend locally
cd backend
pip install -r requirements.txt
python main.py

# Expose via ngrok (separate terminal)
ngrok http 8000
# Copy URL: https://abc-123.ngrok-free.app

# Update frontend API URL
# Rebuild mobile app
```

**Advantages:**
- No cloud build issues
- Works immediately
- Free tier sufficient
- Good for development/testing

## Platform Comparison

| Platform | Python Build | Pydantic v2 | Setup Time | Reliability |
|----------|--------------|-------------|------------|-------------|
| Railway | Poor | ❌ Fails | N/A | Low |
| Render | Good | ✅ Works | 5 min | High |
| Vercel | Good | ✅ Works | 10 min | High |
| Ngrok (local) | N/A | ✅ Works | 2 min | High |

## Detection

You're hitting this issue if Railway build logs show:

```
Building wheel for pydantic-core (pyproject.toml): started
[... compilation errors ...]
✗ Build failed
```

Or:

```
error: could not compile `pydantic-core`
```

## Session Context

Encountered 2026-08-18 when deploying YONDAnime FastAPI backend to Railway. Multiple attempts with different Pydantic versions all failed. Solution: downgraded to Pydantic 1.10.12 with FastAPI 0.100.0, but user ultimately chose ngrok method as faster alternative.

## Recommendation

**For new FastAPI projects:**
- Start with Pydantic v1 (1.10.12) + FastAPI 0.100.0
- Avoid Railway for Python with compiled dependencies
- Use Render or ngrok instead

**For existing projects hitting this:**
- Don't waste time trying newer Pydantic versions on Railway
- Immediately switch to Render or ngrok
- Railway Python support is unreliable for Rust-based packages
