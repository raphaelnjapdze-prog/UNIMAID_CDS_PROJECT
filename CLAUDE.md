# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

"Vector Sentinel Engine" — a Streamlit web app for malaria vector (mosquito) surveillance, built for UNIMAID. It combines field data entry, AI-assisted specimen identification, insecticide-resistance bioassay tracking, clinical-case correlation, forecasting, and reporting. It is a **screening aid, not a validated diagnostic device** — several modules deliberately refuse to claim more precision than the underlying data supports.

## Running the app

```bash
streamlit run app.py
```

Dependencies: `pip install -r requirements.txt`. Note that `requirements.txt` covers the **runtime web app only**. The `models/` training/inference pipeline additionally requires `torch` and `torchvision`, which are intentionally not listed — the deep-learning classifier is a separate, optional workflow (see below) and the deployed app runs without it.

There is no test suite or linter configured. `scripts/test_image_qc.py` is a standalone manual check for `utils/image_quality_control.py`, not a pytest test.

## Configuration & secrets

Secrets are read by `utils/config.py::get_secret(key)`, which checks `st.secrets` (`.streamlit/secrets.toml`) first, then falls back to environment variables / `.env` (via `python-dotenv`). Keys:

- `GEMINI_API_KEY` — Google Gemini (`google-genai` SDK) for vision inference and AI advisory
- `SUPABASE_URL`, `SUPABASE_ANON_KEY` — required for any data persistence
- `SUPABASE_SERVICE_ROLE_KEY` — optional; enables table-creation helpers

If Supabase is not configured, the app must degrade honestly: data-layer functions return `None`/empty DataFrames and callers show a "not connected" state. **Never substitute fabricated data for a missing backend** — this is a hard design rule enforced throughout `utils/data_manager.py`.

## Architecture

### SPA routing (`app.py`)
The app is a single-page application driven by URL query params, not Streamlit multipage. `app.py::main()` reads `?page=<key>`, maps it through `NAV_MAP` to a page name, and calls the matching `render_*_page()` from `components/`. Navigation links (`utils/navigation.py`) always append `&session=active`; this flag is the session-persistence bridge that keeps `st.session_state["authenticated"]` true across Streamlit hot-reloads. To add a page: create `components/<x>.py` with a `render_<x>_page()`, import it in `app.py`, add an entry to `NAV_MAP`, and add a nav item in `utils/navigation.py`.

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
`specimen_records` is the **central table** backing diagnostics, PCR confirmation, accuracy reporting, the dashboard, and site logs. Canonical schema lives in `sql/create_specimen_records.sql`. Other tables: `bioassay_results`, `clinical_case_data`.

Field observations are stored with a `field_screening_result` JSONB column tagged by `screening_method` (`manual_field_log`, `ai_vision`, `manual_checklist`, `trained_classifier`). `data_manager.extract_genus_counts_from_screening()` is the single source of truth for turning any of those shapes into genus counts — reuse it rather than re-parsing the JSON per page. Loads are cached with `@st.cache_data(ttl=60)`; **call the matching `clear_*_cache()` after any write.**

> Schema/table helpers live in `data_manager.py` (`current_supabase_table_status`, `attempt_create_supabase_table`, `supabase_table_exists`) and target `specimen_records`. An older `campus_audit_data` table constant plus matching old-schema helpers in `config.py`/`auth.py` were removed as dead code; don't reintroduce a `SUPABASE_TABLE` constant — the current table is `specimen_records`.

### Taxonomy guardrails (important domain constraint)
Cryptic species complexes (e.g. *An. gambiae* complex, *An. funestus* group, *Culex pipiens* complex) are morphologically indistinguishable and **cannot** be resolved to species by any image classifier — only PCR can split them. Both the Gemini vision path (`utils/vision_inference.py`) and the PyTorch pipeline (`models/`) enforce this via controlled lookup tables and a `resolution_level` field (`genus` / `complex` / `species`). The AI model's raw guess is never trusted to decide whether it crosses into a complex; a deterministic table intercepts it. Downstream code must respect `resolution_level` and never assume species-level precision when it says `complex` or `genus`. See `models/README_CLASSIFIER_SETUP.md`.

### Persistence caution
Some pages write plain files to the app root (e.g. `data/investigator_profile.json`, retraining logs). Avoid adding `debug_*.txt`-style scratch writes to production code paths — they were removed once already. Use logging if you need runtime diagnostics.
