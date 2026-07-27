# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

"Vector Sentinel Engine" — a Streamlit web app for malaria vector (mosquito) surveillance, built for UNIMAID. It combines field data entry, AI-assisted specimen identification, insecticide-resistance bioassay tracking, clinical-case correlation, forecasting, and reporting. It is a **screening aid, not a validated diagnostic device** — several modules deliberately refuse to claim more precision than the underlying data supports.

## Running the app

```bash
streamlit run app.py
```

Dependencies are pinned across three files:
- `requirements.txt` — core runtime for the Streamlit app (pinned `==`).
- `requirements-ml.txt` — heavy, optional ML extras (`torch`, `torchvision`, `opencv-python`) for the `models/` classifier and retraining workflow; all lazy-imported, so the app runs without them. Pulls torch CPU wheels from the PyTorch index.
- `requirements-dev.txt` — dev/CI tooling (`pytest`, `ruff`); also installs core.

```bash
pip install -r requirements.txt        # run the app
pip install -r requirements-dev.txt     # develop / run tests + lint
pip install -r requirements-ml.txt      # additionally, to train/run models
```

## Tests, lint, CI

```bash
pytest                 # unit tests in tests/
ruff check .           # lint (config in pyproject.toml)
ruff check . --fix     # auto-fix
```

Tests live in `tests/` and target the deterministic logic (genus resolution, WHO bioassay thresholds, CSV-injection guard, the local-admin auth fallback) — the pure functions worth locking down. Ruff config is in `pyproject.toml`: rules `E/F/W/I`, `E501` off (legacy embeds long HTML/CSS strings), and `app.py` is exempt from `E402` (Streamlit requires `set_page_config` before page imports). GitHub Actions (`.github/workflows/ci.yml`) runs ruff + pytest on push/PR against Python 3.12 using `requirements-dev.txt`. CI does not install the ML extras — nothing under test imports them.

## Configuration & secrets

Secrets are read by `utils/config.py::get_secret(key)`, which checks `st.secrets` (`.streamlit/secrets.toml`) first, then falls back to environment variables / `.env` (via `python-dotenv`). Keys:

- `GEMINI_API_KEY` — Google Gemini (`google-genai` SDK) for vision inference and AI advisory
- `SUPABASE_URL`, `SUPABASE_ANON_KEY` — required for any data persistence
- `SUPABASE_SERVICE_ROLE_KEY` — optional; enables table-creation helpers

If Supabase is not configured, the app must degrade honestly: data-layer functions return `None`/empty DataFrames and callers show a "not connected" state. **Never substitute fabricated data for a missing backend** — this is a hard design rule enforced throughout `utils/data_manager.py`.

## Architecture

### SPA routing (`app.py`)
The app is a single-page application driven by URL query params, not Streamlit multipage. `app.py::main()` reads `?page=<key>` and looks it up in `PAGE_MODULES`, which maps the key to `"module:render_function"`. **Pages are imported on demand** (`app.py::_render_page` → `importlib.import_module`), not up front: importing all fifteen eagerly dragged in every page's dependencies whether or not it was ever opened (scikit-learn 1.6s for the risk engine, google.genai 1.0s for the Copilot, folium, plotly), making cold start ~9s — paid on every container boot, and Streamlit Cloud reboots idle apps. On-demand import cuts that to ~2.8s; a page's first visit pays its own import, and revisits are free (`sys.modules`). Only `components/login.py` is imported eagerly, since an unauthenticated visitor always renders it.

To add a page: create `components/<x>.py` with a `render_<x>_page()`, add an entry to `PAGE_MODULES` in `app.py` (do **not** add a top-level import — that reintroduces the eager-import cost), and add a nav item in `utils/navigation.py`.

Auth is gated in `main()`: a page renders only if `st.session_state["authenticated"]` (or `guest_explorer`) is set. That flag is set **only** by a real login or by `utils.auth.restore_session()`, which re-validates the stored Supabase tokens against the auth server. There is deliberately no URL-based session flag — the old `?session=active` mechanism was an auth bypass and has been removed. `st.session_state` doesn't survive a full browser reload, so cross-reload persistence goes through `utils/session_cookie.py`: the Supabase **refresh token only** is kept in a `vs_refresh_token` cookie (written from a srcdoc-iframe script, since Streamlit can't set a server-side cookie; read back via `st.context.cookies`). The cookie grants nothing on its own — `restore_session()` hands it to Supabase, which validates it server-side and issues a fresh session; a revoked token gets the caller nowhere. `app.py` calls `sync_refresh_cookie()` once per run to keep it in step, including clearing it on sign-out.

Because of that cookie, the shared Supabase client **must not manage its own session**: `utils/config.py` builds it with `auto_refresh_token=False`. The SDK default (`True`) arms a background thread that refreshes the client's stored session — and since Supabase rotates the refresh token on every refresh, that silently revoked the copy in the user's cookie and handed the replacement only to client memory, so a reload ~an hour after login dumped the user back at the login screen. Don't re-enable it; refreshing is `restore_session()`'s job and it passes the token explicitly.

### Layers
- `components/` — one file per page, each exposing a `render_*_page()`. UI only; delegates data/logic to `utils/`.
- `utils/` — the real logic. Key modules:
  - `config.py` — loads secrets, constructs the shared Supabase client(s), bootstraps session state.
  - `auth.py` — single source of truth for identity. `get_supabase_client()` re-applies the user's access token (from `st.session_state`) on **every** call, because Streamlit reruns can drop the shared client back to anon. Has a local admin fallback when Supabase is off.
  - `data_manager.py` — persistence. All reads/writes go through here.
  - AI/engine modules: `vision_inference.py`, `ai_advisory.py`, `morphology_keys.py`, `pcr_and_accuracy.py`, `epidemiology_engine.py`, `forecasting_engine.py`, `resistance_ml_engine.py`, `weather_engine.py`, `dhis2_client.py`.
  - `theme.py` / `ui_components.py` / `icons.py` / `navigation.py` — presentation.
- `models/` — optional two-stage PyTorch classifier (training + inference), separate from the deployed app.

### Data model (Supabase)
`specimen_records` is the **central table** backing diagnostics, PCR confirmation, accuracy reporting, the dashboard, and site logs. Canonical schema lives in `sql/create_specimen_records.sql`. Other tables: `bioassay_results` (`sql/create_bioassay_results.sql`), `clinical_case_data` (`sql/create_clinical_case_data.sql`) — both of those files are **reconstructions** of tables created by hand in the dashboard first, so the live tables are the authority and may have drifted; each ends with a query that prints the live columns to diff against. Neither has an `updated_at` or an UPDATE policy, because nothing in the app edits those rows — they are inserted, read, and deleted. If you add an edit path, add the trigger and the policy with it.

Field observations are stored with a `field_screening_result` JSONB column tagged by `screening_method` (`manual_field_log`, `ai_vision`, `manual_checklist`, `trained_classifier`, `field_subsample`). Two canonical helpers in `data_manager.py` interpret that column — reuse them rather than re-parsing the JSON per page: `extract_genus_counts_from_screening()` returns `{genus: count}` (the only correct path for `manual_field_log` raw counts), and `extract_primary_genus()` returns the single resolved genus for identification methods (`None` for field logs). Loading goes through the cached `load_specimen_records()` (`@st.cache_data(ttl=60)`); **call the matching `clear_*_cache()` after any write.** `utils/pcr_and_accuracy.py` and `utils/vision_inference.py` still carry their own method-specific presentation/citation logic (resolved-name strings, citations, invasive flags), but **cryptic-complex membership is fully consolidated**: `utils/morphology_keys.py::SPECIES_COMPLEXES` is the single source of truth. `pcr_and_accuracy.py` derives its `COMPLEX_MEMBERSHIP` from it via `complex_membership_by_trigger()`, and `vision_inference.py` derives each `_CRYPTIC_COMPLEXES` entry's `match_terms` from it (keying `_COMPLEX_PRESENTATION` by the canonical `SPECIES_COMPLEXES` name). **Don't reintroduce a hardcoded complex-membership list anywhere** — add members to `SPECIES_COMPLEXES` and all three consumers update together.

#### Subsampling ("vialing out") — the no-double-count invariant
A `manual_field_log` row is a **batch** collection event holding raw genus counts (e.g. 500 Anopheles). To PCR-confirm an individual, it is *vialed out*: `data_manager.py::vial_out_specimens()` creates one child `specimen_records` row per specimen (`specimen_role='individual'`, linked by `parent_specimen_id`, tagged `field_subsample`), whose `specimen_id` **is** its QR/barcode. Migration: `sql/add_specimen_subsampling.sql`.

The invariant everything else depends on: **the batch's raw counts are never mutated.** Instead a `vialed_out` tally is added to the batch's result JSON, and `extract_genus_counts_from_screening()` reports `raw − vialed_out` for the batch while each child contributes 1. Batch + children therefore always conserve the original catch total. If you touch either side of that subtraction, keep `tests/test_subsampling.py::TestGenusCountsWithSubsampling` passing — it pins the conservation property.

Identifying a vialed specimen must **update** its existing row via `attach_identification_to_specimen()`, never insert a new one (that would count the mosquito twice — exactly what subsampling exists to prevent). The Diagnostics page routes every save through `components/diagnostics.py::_save_identification()`, which picks update-vs-insert based on the linked specimen; add new save paths there rather than calling `submit_screening_result` directly. `attach_identification_to_specimen()` refuses to write onto a `manual_field_log` row, since replacing a batch's `field_screening_result` would destroy that collection event's raw counts.

#### Deletion — the same invariant, in reverse
Deleting a specimen row is never just a `DELETE`; the `DELETION` section of `data_manager.py` owns all of it, and new delete paths belong there rather than calling `.delete()` directly. Three things travel with a row: its **photos** (in the `specimen-photos` bucket, not on the row — dropping the row alone orphans objects that keep counting against storage and stay reachable by URL), its **vialed-out children** (`parent_specimen_id` is `on delete set null`, so a plain delete detaches them into individuals whose collection event no longer exists instead of removing them), and its batch's **`vialed_out` tally** (deleting one child decrements it, returning that specimen to the batch — otherwise a real caught mosquito leaves every total). `tests/test_deletion.py` pins the conservation property in both directions; `delete_specimen_records()` returns a summary whose `tally_failures`/`not_deleted` keys must be surfaced, not swallowed. The genus a child was vialed as is read **only** via `subsampled_genus_of()` — an identification overwrites the child's screening result, so it survives under `subsampled_genus`, not in the current result. User-facing docs: `docs/DELETING_ENTRIES.md`.

> RLS makes an `UPDATE` or `DELETE` with no matching policy match zero rows **without raising** — it looks like success. `sql/add_update_policies.sql` and `sql/add_delete_policies.sql` add the policies; every write path here verifies the rows the database actually returned rather than trusting the call. Don't add a mutation that skips that check.

> Schema/table helpers live in `data_manager.py` (`current_supabase_table_status`, `attempt_create_supabase_table`, `supabase_table_exists`) and target `specimen_records`. An older `campus_audit_data` table constant plus matching old-schema helpers in `config.py`/`auth.py` were removed as dead code; don't reintroduce a `SUPABASE_TABLE` constant — the current table is `specimen_records`.

### Taxonomy guardrails (important domain constraint)
Cryptic species complexes (e.g. *An. gambiae* complex, *An. funestus* group, *Culex pipiens* complex) are morphologically indistinguishable and **cannot** be resolved to species by any image classifier — only PCR can split them. Both the Gemini vision path (`utils/vision_inference.py`) and the PyTorch pipeline (`models/`) enforce this via controlled lookup tables and a `resolution_level` field (`genus` / `complex` / `species`). The AI model's raw guess is never trusted to decide whether it crosses into a complex; a deterministic table intercepts it. Downstream code must respect `resolution_level` and never assume species-level precision when it says `complex` or `genus`. See `models/README_CLASSIFIER_SETUP.md`.

The same ceiling is enforced by the deterministic deep-key engines in `utils/morphology_keys.py`: `identify_anopheles_species()` and the couplet walker for *Anopheles*, plus the genus-agnostic `identify_by_characters()` scorer wired up as `identify_culex_species()` / `identify_aedes_species()`, and `evaluate_larval_deepkey()` (genus-only for larvae). Any complex/group winner collapses to the complex/group name with `molecular_id_required=True` — the scorer never manufactures a single-species answer. Complex membership for all of them comes from the one `SPECIES_COMPLEXES` table; the guardrail is pinned by `tests/test_morphology_anopheles.py` and `tests/test_morphology_extended.py`.

### Logging
Use `from utils.logging_config import get_logger` then `logger = get_logger(__name__)` at module top. All loggers sit under a single `vector_sentinel` parent configured once; verbosity is set by the `LOG_LEVEL` env var (default `INFO`). Convention for exception handlers: never silently `pass`/`return None` on a caught exception — log it (`logger.debug(..., exc_info=True)` for non-fatal fallbacks, `warning`/`exception` when a real feature failed), while preserving the fallback control flow. Handlers that already surface the error to the user via `st.error(...)` are not silent and were left as-is (they may additionally log if useful). `logging_config` imports only stdlib to avoid circular imports — don't add app imports to it.

### Persistence caution
Some pages write plain files to the app root (e.g. `data/investigator_profile.json`, retraining logs). Avoid adding `debug_*.txt`-style scratch writes to production code paths — they were removed once already. Use `logger` (above), not file scratch-writes, for runtime diagnostics.
