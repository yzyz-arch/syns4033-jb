"""Global config / paths / constants for A3 Gemini-key farm."""
from __future__ import annotations
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LOGS = ROOT / "logs"
PROFILES = ROOT / "profiles"
for _p in (DATA, LOGS, PROFILES):
    _p.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA / "farm.db"
ACCOUNTS_IN = DATA / "accounts.jsonl"     # input: one google account per line
KEYS_OUT = DATA / "keys.jsonl"            # output: harvested keys
RESULTS = DATA / "claim_results.jsonl"    # per-account run results

# Gemini API endpoints (Generative Language API)
GENLANG_BASE = "https://generativelanguage.googleapis.com/v1beta"
MODELS_URL = GENLANG_BASE + "/models"
GENERATE_URL = GENLANG_BASE + "/models/{model}:generateContent"

# AI Studio / Google Cloud entry points
AISTUDIO_HOME = "https://aistudio.google.com/"
AISTUDIO_APIKEYS = "https://aistudio.google.com/app/apikey"
GCLOUD_PROJECTS_NEW = "https://console.cloud.google.com/projectcreate"
GCLOUD_API_LIBRARY = (
    "https://console.cloud.google.com/apis/library/generativelanguage.googleapis.com"
)

# Login
GOOGLE_ACCOUNTS = "https://accounts.google.com/"

# Default probe/health model + generation model for free-tier farming
DEFAULT_MODEL = os.environ.get("A3_MODEL", "gemini-3.5-flash-lite")
FALLBACK_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.1-flash-lite",
]

# Balancer tuning
MAX_RETRIES_PER_KEY = int(os.environ.get("A3_MAX_RETRIES", "3"))
BACKOFF_BASE = float(os.environ.get("A3_BACKOFF_BASE", "2.0"))
REQUEST_TIMEOUT = int(os.environ.get("A3_TIMEOUT", "90"))

# Region/locale hints for browser profile realism
LOCALES = [
    {"lang": "en-US", "tz": "America/New_York"},
    {"lang": "en-GB", "tz": "Europe/London"},
    {"lang": "en-IN", "tz": "Asia/Kolkata"},
    {"lang": "en-AU", "tz": "Australia/Sydney"},
]
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
)
