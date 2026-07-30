# =========================================================================
# NATIONAL INFORMATION SYSTEM API GATEWAY INTERFACE (utils/dhis2_client.py)
# =========================================================================
import json
import re

import pandas as pd
import requests
import streamlit as st

from utils.config import get_secret
from utils.logging_config import get_logger

logger = get_logger(__name__)

# =========================================================================
# Registry mappings: LGA name -> DHIS2 org unit UID, genus -> data element UID.
#
# These were previously hardcoded dictionaries of invented UIDs — "Hg7824kHGhd",
# "uM8923hGjdf" — that looked exactly like real DHIS2 identifiers and belonged to no
# instance anywhere. A well-formed fake is worse than an obvious placeholder, because it
# invites the reader to trust it. They are gone.
#
# A UID is a fact about one DHIS2 instance, not about a mosquito or a place, so it cannot
# be hardcoded here at all: the same LGA has different UIDs on the demo server and on a
# national instance. Both maps are therefore CONFIGURATION, empty until supplied, read
# from secrets as JSON objects:
#
#     DHIS2_ORG_UNIT_MAP  = '{"Maiduguri": "<uid>", "Jere": "<uid>"}'
#     DHIS2_DATA_ELEMENT_MAP = '{"Anopheles": "<uid>", "Culex": "<uid>"}'
#
# scripts/fetch_dhis2_uids.py queries the configured instance and prints a skeleton to
# fill in. An unmapped name resolves to None and is reported by the caller, never guessed.
# =========================================================================


# A name with no UID is written into the payload as UNMAPPED_<NAME> rather than omitted.
# Omitting it would silently shrink the export — the old `if not org_unit_uid: continue`
# bug. A value that is visibly unmapped can be spotted in the file, counted in the UI, and
# refused by push_data_values, which are three chances to notice.
UNMAPPED_PREFIX = "UNMAPPED_"


def unmapped_code(kind: str, name) -> str:
    """A readable stand-in for a UID that does not exist yet, e.g. UNMAPPED_LGA_JERE."""
    cleaned = re.sub(r"[^A-Z0-9]+", "_", str(name or "UNSPECIFIED").upper()).strip("_")
    return f"{UNMAPPED_PREFIX}{kind.upper()}_{cleaned or 'UNSPECIFIED'}"


def is_unmapped(uid) -> bool:
    """True for a placeholder produced by unmapped_code(), or for a missing UID."""
    return not uid or str(uid).startswith(UNMAPPED_PREFIX)


def _load_uid_map(secret_key: str) -> dict[str, str]:
    """A {name: UID} map from a JSON secret. Empty (not fatal) when unset or malformed.

    An unreadable mapping must not take the app down — the export still runs and reports
    everything as unmapped, which is both true and obvious. A malformed one is logged as a
    warning because it is a configuration mistake, not an expected state.
    """
    raw = (get_secret(secret_key) or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        logger.warning("%s is not valid JSON; treating every name as unmapped", secret_key, exc_info=True)
        return {}
    if not isinstance(parsed, dict):
        logger.warning("%s must be a JSON object of name -> UID; got %s", secret_key, type(parsed).__name__)
        return {}
    return {str(k): str(v) for k, v in parsed.items() if k and v}


def org_unit_for_lga(lga: str | None) -> str | None:
    """The DHIS2 org unit UID for an LGA name, or None if it has no mapping.

    None is a real answer, not a failure: rows logged before the LGA column existed have
    no LGA at all. Callers must report those rather than dropping them, which is what the
    old code did with `if not org_unit_uid: continue` — a silent partial export.
    """
    if not lga:
        return None
    return _load_uid_map("DHIS2_ORG_UNIT_MAP").get(str(lga).strip())


def data_element_for_genus(genus: str | None) -> str | None:
    """The DHIS2 data element UID for a genus, or None if it has no mapping."""
    if not genus:
        return None
    return _load_uid_map("DHIS2_DATA_ELEMENT_MAP").get(str(genus).strip())

def convert_date_to_dhis2_period(date_str):
    """
    Normalizes a standard YYYY-MM-DD date vector into a valid DHIS2
    reporting period format. Default configuration uses daily tracking string formats.
    """
    try:
        parsed_date = pd.to_datetime(date_str)
        # Formats to standard daily parameter ('YYYYMMDD')
        # If your national DHIS2 instance uses monthly reporting aggregates, use: .strftime('%Y%m')
        return parsed_date.strftime('%Y%m%d')
    except Exception:
        logger.debug("Date %r not parseable; using digit-only fallback", date_str, exc_info=True)
        return "".join(filter(str.isdigit, str(date_str)))

def push_data_values(data_values: list, *, dry_run: bool = False, data_set: str | None = None) -> dict:
    """POST a prebuilt list of dataValues to the instance's dataValueSets endpoint.

    Takes the payload rather than building one. The previous version derived its own from a
    wide dataframe (`LGA_District`, `Anopheles_Count`, a Mansonia column the Site Log never
    collects) that no code in this app produced, so it was both dead and a second, divergent
    definition of what a specimen count means. components/dashboard.py::_build_dhis2_payload
    is the one builder now, and it counts via extract_genus_counts_from_screening — so what
    gets submitted is what the dashboard shows.

    `dry_run` sends `dryRun=true`, which validates and reports what *would* import without
    writing. Note it is `dryRun`, not the `importMode=VALIDATE` used by the tracker API —
    dataValueSets silently ignores the latter and performs a real import, which is a
    dangerous way to be wrong. Verified against the demo: the response echoes the flag back
    under `importOptions.dryRun`, so the caller can confirm it was honoured.

    `data_set` names the target dataset. Supply it when a data element belongs to more than
    one: DHIS2 then fails the whole submission with 409 "Data set detection failed, found
    multiple sets".

    Two constraints this cannot fix, both of which reject the submission at the server:
    the period must match the dataset's period type (a Monthly dataset will not take the
    daily YYYYMMDD periods the export produces), and the org unit must be one the dataset is
    actually assigned to — typically a facility, not a district.
    """
    try:
        base_url = st.secrets["DHIS2_ENV"]["BASE_URL"].rstrip("/")
        username = st.secrets["DHIS2_ENV"]["USERNAME"]
        password = st.secrets["DHIS2_ENV"]["PASSWORD"]
    except Exception:
        return {
            "status": "ERROR",
            "message": "Missing authorized DHIS2 authentication variables inside configurations parameters environment."
        }

    target_endpoint = f"{base_url}/api/dataValueSets"

    # A value with no dataElement or no orgUnit cannot be imported, and DHIS2 rejects the
    # whole set rather than the offending entry. Refuse here, naming the count, instead of
    # sending something certain to fail — these are the unmapped LGAs and genera the
    # exporter flags rather than drops.
    incomplete = [
        v for v in data_values
        if is_unmapped(v.get("dataElement")) or is_unmapped(v.get("orgUnit"))
    ]
    if incomplete:
        return {
            "status": "ERROR",
            "message": (
                f"{len(incomplete)} of {len(data_values)} values have no DHIS2 org unit or "
                "data element UID. Map them in DHIS2_ORG_UNIT_MAP / DHIS2_DATA_ELEMENT_MAP "
                "before submitting; nothing was sent."
            ),
        }

    if not data_values:
        return {"status": "WARNING", "message": "Nothing to submit — the payload is empty."}

    body: dict = {"dataValues": data_values}
    if data_set:
        body["dataSet"] = data_set

    try:
        response = requests.post(
            url=target_endpoint,
            headers={"Content-Type": "application/json"},
            auth=(username, password),
            params={"dryRun": "true"} if dry_run else None,
            data=json.dumps(body),
            timeout=35
        )

        summary = _import_summary(response)

        if response.status_code in [200, 201]:
            return {
                "status": "SUCCESS",
                "dry_run": bool(summary.get("importOptions", {}).get("dryRun")),
                "counts": summary.get("importCount") or {},
                "conflicts": _conflict_messages(summary),
                "response_json": summary,
            }
        # A rejected import returns its reasons in the body, and they are the only thing
        # that says *why* — "409 Conflict" alone sent the reader back to the raw JSON.
        return {
            "status": "FAILURE",
            "message": f"DHIS2 rejected the submission (HTTP {response.status_code}).",
            "conflicts": _conflict_messages(summary),
            "details": response.text,
        }

    except requests.exceptions.Timeout:
        return {"status": "ERROR", "message": "The DHIS2 server did not respond in time."}
    except Exception as err:
        logger.warning("DHIS2 submission failed", exc_info=True)
        return {"status": "ERROR", "message": f"Could not reach the DHIS2 server: {err}"}


def _import_summary(response) -> dict:
    """The import summary, which DHIS2 nests under "response" on error and returns flat on
    success. Unwrapped here so callers read one shape."""
    try:
        body = response.json()
    except Exception:
        logger.debug("DHIS2 response was not JSON", exc_info=True)
        return {}
    if not isinstance(body, dict):
        return {}
    nested = body.get("response")
    return nested if isinstance(nested, dict) else body


def _conflict_messages(summary: dict) -> list:
    """Human-readable conflict strings, e.g. "Data set detection failed, found multiple
    sets" or a period that does not match the dataset's period type."""
    conflicts = summary.get("conflicts")
    if not isinstance(conflicts, list):
        return []
    return [str(c.get("value") or c) for c in conflicts if c]
