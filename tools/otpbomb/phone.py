"""Phone number normalisation + request-token helpers.

Everything downstream gets the same four rendered forms so provider templates
never have to think about formatting:

    {e164}   +6281234567890
    {digits} 6281234567890
    {local}  081234567890
    {uuid} / {ts} / {rand16}  request-id filler

Default country is 62 (ID). --cc overrides.
"""
from __future__ import annotations

import re
import time
import uuid

_SEP = re.compile(r"[\s\-().]")
_NON_DIGIT = re.compile(r"\D")


class PhoneError(ValueError):
    pass


def normalise(raw: str, cc: str = "62") -> dict[str, str]:
    """Return the render contexts for `raw`. Raises PhoneError on garbage."""
    if not raw or not raw.strip():
        raise PhoneError("nomor kosong")
    s = _SEP.sub("", raw.strip())
    s = s.replace("+", "")

    if s.startswith("00"):  # 0062.. -> international prefix
        s = s[2:]

    if s.startswith("0"):  # local trunk form -> country code
        s = cc + s[1:]
    elif not s.startswith(cc) and len(s) <= 11:
        # bare subscriber number (812xxxx) -> assume home country
        s = cc + s

    digits = _NON_DIGIT.sub("", s)
    if not 7 <= len(digits) <= 15:
        raise PhoneError(f"panjang tidak valid setelah normalisasi: {digits!r}")

    return {
        "digits": digits,
        "e164": "+" + digits,
        "local": "0" + digits[len(cc):] if digits.startswith(cc) else digits,
        "cc": cc,
        "uuid": uuid.uuid4().hex,
        "ts": str(int(time.time() * 1000)),
        "rand16": uuid.uuid4().hex[:16],
    }


def render_str(text: str, ctx: dict[str, str]) -> str:
    """Substitute {tokens} in a single string (no .format brace collisions)."""
    out = text
    for key, val in ctx.items():
        out = out.replace("{" + key + "}", str(val))
    return out


def render(node, ctx: dict[str, str]) -> object:
    """Recursively substitute {tokens} in str / dict / list / tuple payloads.

    Uses str.replace (not .format) so regex quantifiers like {2,4} survive.
    """
    if isinstance(node, str):
        out = node
        for key, val in ctx.items():
            out = out.replace("{" + key + "}", str(val))
        return out
    if isinstance(node, dict):
        return {render(k, ctx): render(v, ctx) for k, v in node.items()}
    if isinstance(node, (list, tuple)):
        return type(node)(render(v, ctx) for v in node)
    return node
