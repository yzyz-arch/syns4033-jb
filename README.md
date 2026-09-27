<p align="center">
  <img src="assets/banner.png" alt="Hermes Agent" width="100%">
</p>

# hermes-jb ☤
<p align="center">
  <a href="https://github.com/selendang666/selendang666-jb"><b>hermes-jb</b></a> ·
  <a href="https://hermes-agent.nousresearch.com/docs/">Upstream Docs</a>
</p>
<p align="center">
  <a href="https://github.com/selendang666/selendang666-jb"><img src="https://img.shields.io/badge/repo-selendang666%2Fselendang666--jb-FFD700?style=for-the-badge" alt="Repo"></a>
  <a href="https://github.com/NousResearch/hermes-agent/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/selendang666/selendang666-jb/blob/main/scripts/audit_guards.py"><img src="https://img.shields.io/badge/guards-26%2F26%20PASS-brightgreen?style=for-the-badge" alt="Guards 26/26"></a>
</p>

> **Hermes Agent v0.21.3 — jailbreak build.** Fork of [Nous Research's Hermes Agent](https://github.com/NousResearch/hermes-agent) with the guard-rail checklist from spec **HERMES-1** baked in: approvals off, tirith off, redaction off, loop-watchdogs off, uncapped turn/iteration limits, and the SYNS4033 × FOX persona seeded on install. Upstream features, zero guardrails.

---

## What's different from upstream

| Area | Upstream | hermes-jb |
|---|---|---|
| Command approvals | on, confirm destructive | `mode: off`, no confirm |
| Security scanner (tirith) | enabled, fail-closed | disabled, fail-open |
| Secret redaction | on | `redact_secrets: false` |
| Loop watchdogs (gateway) | on | all three off |
| Turn / iteration caps | bounded | `max_turns`/`max_iterations`/`max_tool_calls` = 9999, `max_ticks`/`max_web_searches`/`max_subagents` = 0 (uncapped) |
| Persona | default | SOUL.md / AGENTS.md / USER.md / prefill.json seeded on install |
| Compromised-package advisories | active | neutered (always returns no hits) |
| URL safety | metadata SSRF blocked | metadata/link-local block disabled |
| Prompt-injection threat patterns | 64+ regexes | `_PATTERNS = []` (empty) |

The full guard checklist lives in `setup-hermes.sh` (applied via `hermes config set`) and is machine-verified by `scripts/audit_guards.py`.

---

## Install (fresh VPS / server)

This repo is a manual clone — the upstream `curl … | bash` one-liner does **not** apply here. Use the in-repo setup script:

```bash
git clone https://github.com/selendang666/selendang666-jb.git
cd hermes-jb
./setup-hermes.sh
```

What the script does:

1. Detects desktop/server vs Android/Termux
2. Creates a Python 3.11 virtual environment (in `./venv`; falls back to 3.12/3.13 if 3.11 unavailable)
3. Installs the platform's dependency set
4. Creates `.env` from `.env.example` (if absent)
5. Deploys persona: `SOUL.md`, `AGENTS.md`, `USER.md`, `prefill.json` → `~/.hermes/`
6. Applies the 25-key guard checklist via `hermes config set`
7. Symlinks the `hermes` CLI into a user-facing bin dir
8. Offers the setup wizard (`hermes setup`) at the end

Then reload your shell and start:

```bash
source ~/.bashrc    # or: source ~/.zshrc
hermes setup        # fill in API keys (skip earlier if you answered yes in step 8)
hermes              # start chatting
```

> To skip the wizard at the end of `setup-hermes.sh`, answer `n` (or `echo n | ./setup-hermes.sh`) and run `hermes setup` manually when you're ready.

### After install — 3 user steps

`setup-hermes.sh` does everything **except** your personal credentials. You only fill these in:

```bash
source ~/.bashrc              # 1. reload shell (pick up `hermes` CLI)
hermes setup                  # 2. API keys (required — the script is non-interactive)
hermes gateway install        # 3. optional: Telegram/Discord gateway + cron service
hermes                        # start chatting
```

> **That's it — the jailbreak is pre-baked.** No manual guard patching, no persona copying, no `hermes config set`. Guards are verified at install (`audit_guards.py` → `26/26 PASS`).

### Verify the guards

```bash
python3 scripts/audit_guards.py
```

Expected output ends with:

```
26/26 PASS, 0 FAIL
```

Exit code `0` means every guard matches the baked spec. Re-run it any time after changing `~/.hermes/config.yaml`.

### Gateway (Telegram / Discord / …)

```bash
hermes gateway install   # install as a service + cron scheduler
```

### Skills

This repo ships **all bundled skills pre-embedded** under `skills/` — 1,164 skill folders (upstream categories + `hacktricks_skills/` + your custom packs: `syns4033-skills`, `hermes-skill-pack`, `fox`).

**No manual copying needed** — `setup-hermes.sh` syncs them into `~/.hermes/skills/` automatically (via `tools/skills_sync.py`, with a `cp -rn` fallback):

```bash
./setup-hermes.sh   # step: "Syncing bundled skills to ~/.hermes/skills/ ..."
```

To re-sync later or point Hermes at external dirs instead:

```bash
# Re-sync bundled skills after a pull
venv/bin/python tools/skills_sync.py

# Or point Hermes at external skill dirs (survives repo skill updates)
hermes config set skills.external_dirs '["~/syns4033-skills", "~/hermes-skill-pack", "~/fox"]'
```

---

## Getting Started

```bash
hermes              # Interactive CLI — start a conversation
hermes model        # Choose your LLM provider and model
hermes tools        # Configure which tools are enabled
hermes config set   # Set individual config values
hermes config get   # Print individual config values
hermes gateway      # Start the messaging gateway (Telegram, Discord, etc.)
hermes setup        # Run the full setup wizard (configures everything at once)
hermes update       # Update to the latest version
hermes doctor       # Diagnose any issues
```

📖 **[Full documentation →](https://hermes-agent.nousresearch.com/docs/)** (upstream docs — still accurate for features/CLI)

---

## CLI vs Messaging Quick Reference

Hermes has two entry points: start the terminal UI with `hermes`, or run the gateway and talk to it from Telegram, Discord, Slack, WhatsApp, Signal, or Email.

| Action | CLI | Messaging platforms |
| --- | --- | --- |
| Start chatting | `hermes` | `hermes gateway setup` + `hermes gateway start`, then message the bot |
| Start fresh conversation | `/new` or `/reset` | `/new` or `/reset` |
| Change model | `/model [provider:model]` | `/model [provider:model]` |
| Set a personality | `/personality [name]` | `/personality [name]` |
| Retry or undo last turn | `/retry`, `/undo` | `/retry`, `/undo` |
| Compress context / usage | `/compress`, `/usage`, `/insights [--days N]` | `/compress`, `/usage`, `/insights [days]` |
| Browse skills | `/skills` or `/<skill-name>` | `/<skill-name>` |
| Interrupt current work | `Ctrl+C` or new message | `/stop` or new message |

---

## Troubleshooting

**`agent.max_turns` shows 9999 but your live config says otherwise?**
`scripts/audit_guards.py` verifies the *baked defaults* in `hermes_cli/config_defaults.py` (what a fresh install gets), not your already-modified `~/.hermes/config.yaml`. To re-apply the guard values to an existing install:

```bash
# re-run the guard block from setup, or set keys manually, e.g.:
hermes config set agent.max_turns 9999
```

**Updater / advisory check seems dead?**
Expected — `detect_compromised()` is neutered in this build and update checks are part of the disabled guard surface.

**Skill pack not showing up?**
`skills/` in this repo is the upstream set only. Custom packs must be installed via `skills.external_dirs` or copied into `~/.hermes/skills/` (see [Skills](#skills)).

---

## Relationship to upstream

This is a private/unofficial build. Bugs in Hermes itself should go to [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent/issues) — this fork deliberately disables security features, so don't expect guard behavior here to match upstream docs.

---

## License

MIT — see [LICENSE](LICENSE).

Upstream built by [Nous Research](https://nousresearch.com).
