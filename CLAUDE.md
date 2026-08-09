# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Read `AGENTS.md` first — it is the canonical, maintained development guide** (contribution rubric, footprint ladder, plugin/skill/toolset policies, known pitfalls, testing rules). `apps/desktop/AGENTS.md` covers the Electron desktop app. This file is a quick orientation + command reference; when they disagree, AGENTS.md wins.

## What Hermes Is

A personal AI agent running one agent core across a CLI, a messaging gateway (~20 platforms), an Ink TUI, and an Electron desktop app. Two invariants shape every change:

- **Per-conversation prompt caching is sacred.** Never mutate past context, swap toolsets, or rebuild the system prompt mid-conversation (only exception: context compression). Also preserve strict message role alternation — never two same-role messages in a row.
- **The core is a narrow waist; capability lives at the edges.** Every core model tool ships on every API call. New capability goes up the "Footprint Ladder" (AGENTS.md): extend existing code → CLI command + skill → service-gated tool (`check_fn`) → plugin → MCP catalog → new core tool (last resort).

## Commands

### Python tests

**ALWAYS use `scripts/run_tests.sh` — never call `pytest` directly.** It enforces CI parity (credentials unset, temp `HERMES_HOME`, TZ=UTC, per-file subprocess isolation).

```bash
scripts/run_tests.sh                                     # full suite
scripts/run_tests.sh tests/gateway/                      # one directory
scripts/run_tests.sh tests/agent/test_foo.py -k test_x   # one test (file + -k)
scripts/run_tests.sh -v --tb=long                        # pass-through pytest flags
```

The runner probes `.venv`, then `venv`, then `~/.hermes/hermes-agent/venv`. Setup: `uv pip install -e ".[all,dev]"`. Integration tests are excluded by default (`-m 'not integration'`).

### Python lint/typecheck

```bash
ruff check .        # only PLW1514 enforced: explicit encoding= on open()/read_text()
ty check            # type checker (dev extra)
```

### JS/TS (npm workspaces: `apps/*`, `ui-tui`, `web`, `tests-js`)

```bash
npm install                      # at repo root (workspaces install)
npm run check                    # typecheck + test + lint across all workspaces
npm run fix                      # lint --fix (+ prettier where defined)
# Per workspace (cd ui-tui | web | apps/desktop | tests-js):
npm run typecheck / test / lint  # vitest for tests
npx vitest run path/to/file.test.ts   # single JS test file
cd ui-tui && npm run dev         # TUI watch mode
cd apps/desktop && npm run dev   # desktop app (renderer + electron)
```

Tests that assert about `package.json`/`.ts`/`.tsx`/JS artifacts belong in the vitest suite (`tests-js/` or the workspace), NOT in `tests/*.py` — the CI change classifier won't run Python tests on JS-only PRs.

## Architecture (big picture)

```
tools/registry.py  →  tools/*.py (self-register at import)  →  model_tools.py  →  run_agent.py / cli.py / gateway
```

- `run_agent.py` — `AIAgent` class, the synchronous core conversation loop (`run_conversation()`); OpenAI message format; agent-level tools (todo, memory) intercepted here before `handle_function_call()`.
- `model_tools.py` — tool orchestration, discovery, plugin hook invocation. Importing it triggers plugin discovery (`discover_plugins()` is idempotent — call it explicitly on paths that don't import model_tools).
- `toolsets.py` — `TOOLSETS` dict + `_HERMES_CORE_TOOLS`. Registering a tool is not enough; it must appear in a toolset to be exposed to the model.
- `cli.py` — `HermesCLI` (classic prompt_toolkit CLI). Slash commands live in a central `COMMAND_REGISTRY` in `hermes_cli/commands.py`; every consumer (CLI dispatch, gateway, Telegram menu, Slack, autocomplete, help) derives from it.
- `gateway/` — messaging gateway (`run.py`, `session.py`, `platforms/<platform>.py` adapters).
- `ui-tui/` (Ink/React, owns the screen) + `tui_gateway/` (Python JSON-RPC backend over stdio, owns sessions/tools/model calls) — `hermes --tui`. The dashboard (`web/`) embeds this real TUI over a PTY WebSocket; do not rebuild the chat transcript/composer in React.
- `apps/desktop/` — separate Electron chat surface talking JSON-RPC to a headless `hermes serve` backend; shares transport via `apps/shared` (`@hermes/shared`).
- `agent/` — provider adapters, memory manager/providers, compression, auxiliary LLM clients, curator.
- `plugins/` — several discovery systems: general plugins (`hermes_cli/plugins.py`, `register(ctx)` + lifecycle hooks), memory providers (`agent/memory_provider.py` ABC), model providers (`plugins/model-providers/`, lazy-discovered by `providers/__init__.py`, NOT by PluginManager). Plugins must never modify core files. New memory providers and third-party-product plugins are NOT accepted in-tree — they ship as standalone plugin repos.
- `skills/` (bundled) and `optional-skills/` (shipped, not active by default). Skill authoring standards in AGENTS.md are hardline (description ≤ 60 chars, section order, tests at `tests/skills/test_<skill>_skill.py`).
- `cron/` — scheduler; `hermes_state.py` — SQLite session store (FTS5).

## Rules that bite

- **Profiles:** use `get_hermes_home()` / `display_hermes_home()` from `hermes_constants` — never hardcode `~/.hermes` or `Path.home() / ".hermes"`. Tests must never write to `~/.hermes/` (autouse fixture redirects `HERMES_HOME`).
- **Config:** `.env` is for secrets ONLY. All behavioral settings go in `config.yaml` (`DEFAULT_CONFIG` in `hermes_cli/config.py`). Don't add new `HERMES_*` env vars for non-secret config. Three config loaders exist (CLI, `hermes_cli/config.py`, gateway raw YAML) — a key visible in one and not another means you're on the wrong loader.
- **Dependencies:** core deps in `pyproject.toml` are exact-pinned (`==X.Y.Z`); never add a bare `>=` without a ceiling; run `uv lock` after changes. Opt-in backends go in extras + `tools/lazy_deps.py`, not core deps.
- **Tests:** no change-detector tests (snapshots of model lists, config version literals, counts) — assert invariants/relationships instead. Never read source-file text in a test — extract the logic and call it. A `⚠ FLAKY` retry-pass is a bug to fix.
- **New handlers must return JSON strings** (tool registry contract); new interactive menus use `hermes_cli/curses_ui.py` (not `simple_term_menu`).
- **Surface capability is a property of the session, not the process env** — never gate tools on env vars like `HERMES_DESKTOP=1`; use named toolsets resolved from the session's platform.
- Cache-mutating slash commands default to deferred invalidation with an opt-in `--now` flag.
