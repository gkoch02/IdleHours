# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. It holds working notes and invariants; the references it links to are the one home for everything else, so follow the link rather than restating a fact here.

## What This Is

Idle Hours is an end-to-end literary-clock system: it harvests time-related quotes from Project Gutenberg, scores and cleans them, then picks and renders a quote for any clock time. The render is designed for a Pimoroni Inky Impression 7.3 Spectra 6 eInk panel (800×480, 6-color palette) but writes a plain PNG first, so it runs fine on any machine.

Every stage is a standalone Python 3 CLI script that reads/writes JSONL. The mining/selection pipeline is stdlib-only; `render_quote` pulls in Pillow, and `display_inky.py` additionally needs the Pimoroni `inky` package (Pi only).

## Where things are documented

| Topic | Home |
|---|---|
| Operator path: install, CLI, config file, quiet hours, buttons, curator UI, Pi deployment, the theme table | [`README.md`](README.md) |
| Corpus pipeline (mining → bake), every pipeline command, data model, quote selection, overrides, anti-repeat ledger, contact sheet | [`docs/pipeline.md`](docs/pipeline.md) |
| Runtime loop, default-path resolution, config precedence, quiet hours, themes at runtime, buttons, state, telemetry, supervision | [`docs/runtime.md`](docs/runtime.md) |
| Renderer, per-theme design notes, bundled-font table | [`docs/themes.md`](docs/themes.md) |
| Spectra 6 colour recipes | [`docs/spectra6_color_recipes.md`](docs/spectra6_color_recipes.md) |
| Curator web UI: endpoints, security model, curation semantics | [`docs/web_ui.md`](docs/web_ui.md) |
| Test suite, fences, CI jobs | [`docs/testing.md`](docs/testing.md) |
| Dev setup, contribution workflow, releases | [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) |
| Pi hardware and OS setup | [`docs/pi_setup_inky_impression.md`](docs/pi_setup_inky_impression.md) |

**Single-source, don't fence.** When two Python modules need the same list or constant, import it from one place (`theme_names.THEME_ORDER`, `pick_quote.BAKED_SCORE_COMPONENTS`). A sync test is for copies that *must* exist outside Python (README rosters, `config.toml.*`, docs tables); it is not a substitute for an import. If an import would drag in a heavy dependency, move the constant down to a lighter module rather than copying it (issue #394). A test's own hand-written expected values are not copies in this sense: they are the independent oracle (`CUSTOM_FRAME_THEMES`, the literals pinning `recent_window_size`), and reading the expectation back from the code under test makes the test unable to fail (issue #392).

**Don't write counts of registry members into prose** ("eighty-nine themes", "37 border painters"). Write "every theme in `THEME_ORDER`" or point at the registry. A count is a cache of `len()`; it drifts, and no test parses prose for a number (issue #352). Rosters a reader needs (the README theme table, the button-B chain) are fenced by `tests/test_docs_theme_registry.py`.

## Common Commands

```bash
pip install -e ".[dev]"     # dev install; registers the `idle-hours` console script

# Run the full test suite (CI runs it in parallel with -n auto; single-threaded takes a few minutes)
pytest

# Match CI: parallel + coverage on Python 3.12 (uses sys.monitoring tracer)
COVERAGE_CORE=sysmon pytest -n auto --dist loadscope --cov=idle_hours --cov-report=term-missing

# Run a specific test module
pytest tests/test_pick_quote.py

# Run ruff linter (checks E, W, F, I, B; line-length 130); --fix for import ordering
ruff check .

# Type-check the package (settings in pyproject.toml's [tool.mypy])
mypy

# Regenerate derived docs/assets after a change that affects them
UPDATE_RENDER_GOLDEN=1 pytest tests/test_render_golden.py     # golden renders
python3 scripts/generate_theme_previews.py --theme NAME          # README preview (--check in CI)
python3 scripts/generate_font_table.py                           # docs/themes.md font table
```

`idle-hours --help` lists every subcommand; `idle-hours <sub> --help` forwards to the backing module's argparse, and `python3 -m idle_hours.<module>` is the equivalent spelling. Everyday runtime invocations (`idle-hours run --once`, `idle-hours render --time 14:30`, `idle-hours pick --time 14:30`, `idle-hours health --hours 24`, `idle-hours contact-sheet`) are in the README; the full flag reference is in `docs/runtime.md`; the pipeline commands, in stage order, are in `docs/pipeline.md`.

## Default paths

Full rules in [`docs/runtime.md`](docs/runtime.md) ("Default paths"). The invariants:

- **Bundled package assets** (`idle_hours/assets/`, `fonts/`, `web/`) and per-stage default JSONL paths anchor on `BASE_DIR`, which is *inside* the installed package.
- **Runtime artefacts** (`output/current.png`, `data/gutenberg/`, history / state / telemetry) anchor on **CWD**, never `BASE_DIR`: writing into site-packages is never what an operator wants. The appliance preset uses absolute `/var/lib/idle-hours/` paths.
- **Operator-supplied inputs** (`--render-script`, `--display-script`, `--quiet-image`, `--startup-image`) go through `path_resolution.resolve_input_path`: CWD first, bundled fallback. Absolute paths pass through.
- **The bundled renderer is a module, not a path.** `--render-script "auto"` runs `python -m idle_hours.render_quote`; `runtime_render._render_command` is the one place that decides, including the legacy `"render_quote.py"` spellings (issues #335, #364).

## Corpus & selection

Full reference: [`docs/pipeline.md`](docs/pipeline.md). Pipeline order: miner → merge → (coverage → targeted sweep → import → merge) → clean → quality → (legacy fixers) → enrich → `apply_content_overrides` → `bake_quote_database` → picker.

- **Source of truth is the raw corpus (`idle_hours/assets/candidates-attributed.jsonl`) + `content_overrides.json`.** The baked `quote_database.jsonl` is derived; never edit it by hand.
- **Runtime reads the baked DB; a raw-corpus change without a re-bake is invisible to the panel.** Commit the bake with the corpus. Bump `BAKED_SCORE_SCHEMA_VERSION` whenever `BAKED_SCORE_COMPONENTS` changes; both are defined once in `pick_quote`, which the baker imports them from, and `tests/test_bake_equivalence.py` asserts baked and raw picks agree.
- **The curator UI reads the raw corpus on purpose** (`/api/bucket`, `/api/search`), so an operator can see rows the baker dropped. Don't switch it to the baked DB.
- **Every picker default path is absolute and exists.** A CWD-relative default once made the runtime silently ignore every ban (`TestOverridesPathDefaults`).
- **The four corpus paths are relocatable** (`--overrides` / `--content-overrides` / `--raw-corpus` / `--baked-db`) and must reach *both* the picker and the curator UI from the same Namespace; splitting them lets the UI write a file the panel never reads. Relocated sidecars are seeded once and never rewritten; a relocated raw corpus / baked DB is rebuilt from a changed bundle at startup, under the pidfile, with the operator's content overrides re-applied and newly shipped content fixes folded in (`_refresh_relocated_corpus`, `--freeze-corpus` opts out).
- **`buckets.py` is the single source of truth** for the bucket table and the rounding rule `((minute + 2) // 5) * 5`. Never add a second state table.
- **A `(source_id, line_number)` key does not identify a row**: one line can carry several time phrases. Pins carry `matched_text` too (`TestPinFidelityAgainstShippedCorpus`), and bans / the anti-repeat ledger reach a row's textual twins.
- **Sidecar loaders fail open** (a truncated `selection_overrides.json` / `content_overrides.json` warns and degrades, never crashes the loop); writers go through `atomic_io`. Content overrides are reversible via `override_originals`.
- **A row reaches the panel only if the renderer can highlight its `matched_text`.** `match_span.has_display_match` (stdlib-only) is the one test; the renderer, the baker, the raw picker and the coverage report all call it, so raw and baked picks stay equal (issue #411).
- **Push recurring fixes upstream.** If you are overriding more than a handful of rows for the same reason, fix the miner / cleaner / quality filter instead.

## Architecture

### Rendering (`render_quote/`)

Imports `pick_quote` in-process and lays out an 800×480 RGB PNG snapped to the six Spectra 6 inks. **Full reference, including the theme architecture, the "Adding a theme" checklist, the conventions every theme follows, every theme's design notes, the font chains and the colour recipes, is [`docs/themes.md`](docs/themes.md).** Read the relevant theme's entry there before touching its painter; most entries record approaches that were tried and rejected, and why. Theme design notes live there only: a theme module's header is a few lines and links there (issue #399).

Invariants that bite before you reach the doc:

- A theme is exactly one of border-painted (`BorderSpec`), custom-framed (`FrameSpec` naming `render_<theme>_frame`) or deliberately plain; `registry` fails at import on an unclaimed, double-claimed or unknown theme. A theme module never imports another theme module; shared code goes in `themes/_shared.py`.
- **On-palette only**, judged on the calibrated panel inks, not an RGB screenshot. Off-palette colours are stippled from two or three inks (`docs/spectra6_color_recipes.md`).
- **Determinism.** Frames are byte-identical across processes: never `hash()`, seed from `_row_digest`, and read the clock only through `clock.now()` via its module, with the theme listed in `CLOCK_DEPENDENT_THEMES`. `scripts/render_fingerprint.py` checks a pure code move.
- **Time surfaces.** The matched phrase carries the time; never print HH:MM digits unless the object is a clock. Hour-only carriers are byte-identical across the minutes of an hour. A time-drawing theme goes in `theme_names.TIME_SURFACE_THEMES`, a name-printing one in `BRANDED_THEMES`.
- **Reuse the shared helpers** in `themes/_shared.py` and `furniture` before writing a new one; a new `_<theme>_hour` or `_<theme>_seed` is a smell (issue #336).

### Runtime Loop (`run_clock.py`)

**Full reference: [`docs/runtime.md`](docs/runtime.md)**: the tick, config precedence, quiet hours, theme resolution, buttons, persisted state, telemetry, backoff, the watchdog, shutdown and the per-module ownership / lock / thread tables. Read it before changing any `runtime_*` module.

- **Every repaint pins the displayed quote** (`displayed_quote(state)`) and never re-peeks; a peek is history-filtered and returns a different row.
- **Quiet hours:** `render_quiet_frame` is the one sleep-frame path, `claim_quiet_edge` the one edge detector, and whoever paints the frame claims the edge. `resolve_quiet_theme` decides what shows while asleep.
- **Identity triple** `(last_bucket, last_quote_id, last_effective_theme)` is committed only through `commit_render_result` after a successful render; transient modes (`card`) never commit. The few direct writes are listed in the doc.
- **Three locks:** `render_lock` (coarse; buttons and web take it non-blocking via `_button_render_gate`), `state.lock` (may nest inside `render_lock`), `ledger_lock` (never nested). Never hold `state.lock` or `ledger_lock` across a subprocess.
- **All actions converge:** GPIO buttons and web POSTs both call `runtime_actions.action_*` → `_button_render_gate` → `_render_unlocked` → `commit_render_result`. There is no separate web path.
- **Read helpers through their module** (`runtime_render.render_now(...)`, never a name import) so a single patch reaches every caller. Nothing under `idle_hours/` except `idle_hours_cli` imports `run_clock`, which re-exports nothing (`tests/test_runtime_layering.py`).
- **Config:** CLI > config > argparse default via `parser.set_defaults`. A new flag must be wired into `CONFIG_SCHEMA` (or `TRANSIENT_KEYS`), `config.toml.defaults` and `config.toml.example`; tests enforce each. `CONFIG_SCHEMA` is a hand copy of the parser's dests; don't model new code on it.
- **Durability:** every file the next tick reads is written through `atomic_io`; a `fcntl` pidfile guards the loop; subprocesses run under timeouts and SIGTERM drains the in-flight render.

### Inky Display Bridge (`display_inky.py`)

Pillow → Pimoroni `inky.auto` bridge, retried on I/O hiccups, Pi only. `THEME_SATURATION` gives every theme `0.5` (light ground) or `0.7` (dark, coloured or bloom-heavy ground); exceptions carry a one-line reason in the table and a test checks both the rule and the list. A new theme with no row fails `test_every_render_theme_has_saturation`.

### Curator Web UI (`web_server.py`, `idle_hours/web/`)

**Full reference: [`docs/web_ui.md`](docs/web_ui.md)**: endpoints, security model, connection limits, bake / ban / overrides semantics. **Maintenance-only:** fix breakage and security issues, no feature or polish work until someone uses it. It runs **inside `run_clock`** and shares `RuntimeState`; in-process is non-negotiable because mutating POSTs go through the same `_button_render_gate` as the buttons. Any non-loopback bind requires a token; POSTs need `Content-Type: application/json`, a matching `Origin`, and an allowed `Host`.

### Appliance, Container, Releases

- **Fresh Pi:** `scripts/bootstrap_pi_inky.sh` in two passes around a reboot; the long-form guide is [`docs/pi_setup_inky_impression.md`](docs/pi_setup_inky_impression.md). `tests/test_pi_deployment_contract.py` pins the script, the unit and the appliance config as string fences, so read it before changing any of them.
- **Service:** `ops/idle-hours.service.example`. `WorkingDirectory=` and `Environment=LG_WD=` must stay equal (`lgpio` opens its button FIFO relative to CWD); only `User=` and the interpreter path are install-specific.
- **Container:** `Dockerfile` is a multi-stage, ARM64-first build without the `[pi]` extra; the run command is in the README.
- **Releases:** `scripts/release.py prepare` / `finalize`; it never publishes and never pushes without `--push` (`docs/CONTRIBUTING.md`).

### Testing

**Full reference: [`docs/testing.md`](docs/testing.md)**: suite layout, golden fixtures, the structural fences, the JS suite, packaging tests and the CI matrix.

- One `tests/test_<module>.py` per module, class-based. Build a `run_clock` Namespace with `make_args(tmp_path, **overrides)` from `tests/conftest.py`, never `argparse.Namespace(...)` by hand (issue #396).
- **Patch where a name is read.** Writes through the `render_quote` facade raise; patch the submodule that reads the name (`themes.culture.paint_neon_mask`, `runtime_render.render_now`). Full rule in `docs/testing.md`.
- **Golden renders:** `tests/golden/renderer/*.png`, regenerated with `UPDATE_RENDER_GOLDEN=1 pytest tests/test_render_golden.py`. README previews must stay current (`scripts/generate_theme_previews.py --check`).
- **Structural fences fail on absence**, not just change: a painter that paints nothing, a doc roster regex that matches nothing, a stale font table, a CI job that is neither required nor advisory.
- **Idle Weather imports from this package.** `tests/test_downstream_contract.py` lists what it uses; change both repos together.
- **Pixel assertions** use `tests/pixel_helpers.py`, never `Image.getdata()`. Per-pixel access goes through `palette.pixel_access` / `gray_pixel_access` / `rgb_pixel_access`, never a bare `image.load()`, so `mypy` stays clean.
- **CI** (`.github/workflows/ci.yml`): `lint`, `typecheck`, `test (3.11)`, `test (3.12)`, `golden-render`, `web-ui-js`, `package-build` are required; `coverage` and `release-version` are advisory.

### Repo Layout

Everything the wheel ships lives under the single `idle_hours/` package (`pyproject.toml` is the source of truth for its contents); `scripts/`, `docs/`, `ops/` and `tests/` stay at the root, and `output/` and `data/` are runtime artefacts. The README's "Repo map" describes each module. When editing:

- `render_quote/` is a layered package: `_paths → clock → palette → theme_tables → fonts → layout → text → primitives → furniture → themes/_shared → themes/<name>.py → registry`, each layer importing only from those before it (`docs/render_quote_split.md`, fenced by `tests/test_render_quote_layering.py`). `core` holds `render()`, the source card, the sleep frame and the CLI.
- `run_clock.py` is a thin orchestrator over the `runtime_*` modules (config, state, store, telemetry, theme, quiet, render, actions, log), each owning one concern; the ownership table is in `docs/runtime.md`.
- `theme_names.py` is the Pillow-free theme roster; `buckets.py` the bucket table; `atomic_io.py` and `jsonl_io.py` the shared I/O primitives.
- `assets/` holds the baked and raw corpus, the sidecars, the two `config.toml.*` copies, the committed raster plates (regenerated by `scripts/generate_*_plate.py` / `ingest_*.py`, never by hand) and the README previews.
