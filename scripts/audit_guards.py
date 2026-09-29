#!/usr/bin/env python3
"""Guard checklist audit — verifies guard keys match the setup-hermes.sh
_checklist AND (optionally) the live ~/.hermes/config.yaml.

Run from anywhere inside a repo checkout:
    python3 scripts/audit_guards.py            # baked defaults (hermes_cli/config_defaults.py)
    python3 scripts/audit_guards.py --live     # live ~/.hermes/config.yaml
    python3 scripts/audit_guards.py --both     # baked + live (default when --live given)

Exit 0 = all checks pass, exit 1 = mismatch/missing.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from hermes_cli import config_defaults  # noqa: E402

try:
    from agent import agent_init  # noqa: E402
    CLAMP_SRC = str(agent_init.__file__)
except Exception:
    CLAMP_SRC = str(REPO / "agent" / "agent_init.py")

# (section_tuple_or_key, expected_value)  — mirrors setup-hermes.sh _GUARD_SETS
CHECKS = [
    (("approvals", "mode"), "off"),
    (("approvals", "destructive_slash_confirm"), False),
    (("security", "tirith_enabled"), False),
    (("security", "tirith_fail_open"), True),
    (("security", "redact_secrets"), False),
    (("security", "allow_private_urls"), True),
    (("security", "protected_instruction_files"), False),
    (("browser", "allow_private_urls"), True),
    (("tool_loop_guardrails", "warnings_enabled"), False),
    (("tool_loop_guardrails", "hard_stop_enabled"), False),
    (("tool_loop_guardrails", "non_interactive_hard_stop_enabled"), False),
    (("tool_loop_guardrails", "loop_caps", "max_web_searches"), 0),
    (("tool_loop_guardrails", "loop_caps", "max_subagents"), 0),
    (("gateway", "loop_watchdog"), False),
    (("gateway", "startup_watchdog"), False),
    (("gateway", "bot_loop_guard", "enabled"), False),
    (("loops", "max_ticks"), 0),
    (("loops", "max_web_searches"), 0),
    (("loops", "max_subagents"), 0),
    (("agent", "max_turns"), 9999),
    (("goals", "max_turns"), 9999),
    (("delegation", "max_iterations"), 9999),
    (("code_execution", "max_tool_calls"), 9999),
    (("compression", "max_attempts"), 99),
    (("compression", "threshold"), 0.75),
    (("compression", "target_ratio"), 0.45),
    (("compression", "protect_last_n"), 40),
    (("compression", "min_tail_user_messages"), 3),
    (("compression", "tail_mode"), "lean"),
    (("compression", "proactive_prune_tokens"), 0),
    ("hooks_auto_accept", True),
]

# Spec HERMES-1 VERIFICATION CHECKLIST — subset of CHECKS (keys the spec
# explicitly lists in its grep + expected values).
SPEC_CHECKLIST_KEYS = {
    ("approvals", "mode"),
    ("security", "tirith_enabled"),
    ("tool_loop_guardrails", "warnings_enabled"),
    ("tool_loop_guardrails", "hard_stop_enabled"),
    ("tool_loop_guardrails", "non_interactive_hard_stop_enabled"),
    ("gateway", "loop_watchdog"),
    ("gateway", "startup_watchdog"),
    ("gateway", "bot_loop_guard", "enabled"),
    ("loops", "max_web_searches"),
    ("loops", "max_subagents"),
    ("agent", "max_turns"),
    ("code_execution", "max_tool_calls"),
    ("delegation", "max_iterations"),
    ("compression", "max_attempts"),
}


def _resolve(cfg, path):
    """Return (found, value) for a dotted path in nested dict."""
    node = cfg
    if isinstance(path, tuple):
        parts = path
    else:
        parts = (path,)
    for p in parts:
        if not isinstance(node, dict) or p not in node:
            return False, None
        node = node[p]
    return True, node


def _check_dict(source_label, cfg, only_spec=False):
    passed = failed = 0
    checks = [c for c in CHECKS
              if not only_spec or (isinstance(c[0], tuple) and c[0] in SPEC_CHECKLIST_KEYS)
              or (not isinstance(c[0], tuple) and c[0] == "hooks_auto_accept" and not only_spec)]
    for path, want in checks:
        found, node = _resolve(cfg, path)
        label = ".".join(path) if isinstance(path, tuple) else path
        if not found:
            print(f"MISSING {label} (want {want})   [{source_label}]")
            failed += 1
            continue
        ok = node == want
        print(f"{'PASS' if ok else 'FAIL'} {label} = {node!r}"
              + ("" if ok else f" want {want!r}")
              + f"   [{source_label}]")
        passed += ok
        failed += not ok
    return passed, failed


def _check_clamp():
    raw = Path(CLAMP_SRC).read_text(encoding="utf-8")
    if "min(max_attempts, 99)" in raw:
        print("PASS agent_init compression clamp = min(max_attempts, 99)")
        return 1, 0
    print("FAIL agent_init compression clamp is not min(max_attempts, 99)")
    return 0, 1


def main(argv):
    live = "--live" in argv
    baked = "--baked" in argv
    both = "--both" in argv
    # default: baked only (backwards compatible)
    if not (live or baked or both):
        baked = True
    if both:
        baked = live = True

    total_pass = total_fail = 0

    if baked:
        print("=== BAKED DEFAULTS (hermes_cli/config_defaults.py) ===")
        p, f = _check_dict("baked", config_defaults.DEFAULT_CONFIG)
        total_pass += p
        total_fail += f

    if live:
        import yaml
        live_path = Path.home() / ".hermes" / "config.yaml"
        if not live_path.exists():
            print(f"\n=== LIVE ({live_path}) ===")
            print(f"MISSING file {live_path} — cannot audit live config")
            total_fail += 1
        else:
            try:
                with open(live_path, encoding="utf-8") as fh:
                    live_cfg = yaml.safe_load(fh) or {}
            except Exception as exc:
                print(f"\n=== LIVE ({live_path}) ===")
                print(f"ERROR parsing {live_path}: {exc}")
                total_fail += 1
            else:
                print(f"\n=== LIVE ({live_path}) ===")
                p, f = _check_dict("live", live_cfg)
                total_pass += p
                total_fail += f

    # runtime clamp (only meaningful with baked)
    if baked:
        p, f = _check_clamp()
        total_pass += p
        total_fail += f

    total = total_pass + total_fail
    print(f"\n{total_pass}/{total} PASS, {total_fail} FAIL")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
