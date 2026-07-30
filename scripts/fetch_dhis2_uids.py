"""Print the org unit and data element UIDs of the configured DHIS2 instance.

A DHIS2 UID is a fact about one instance — the same LGA has different UIDs on the demo
server and on a national one — so `utils/dhis2_client.py` holds no UIDs at all and reads
them from two JSON secrets instead. This script queries the instance named in
DHIS2_ENV.BASE_URL and prints what it actually has, so those secrets can be filled in from
real values rather than guessed.

    python scripts/fetch_dhis2_uids.py                    # org units at level 2
    python scripts/fetch_dhis2_uids.py --level 3
    python scripts/fetch_dhis2_uids.py --data-elements malaria
    python scripts/fetch_dhis2_uids.py --skeleton         # a DHIS2_ORG_UNIT_MAP to paste

Read-only: it issues GETs and never writes to the instance.
"""
import argparse
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.geography import BORNO_LGAS  # noqa: E402


def _credentials():
    """(base_url, auth) from secrets.toml, read directly.

    Deliberately not via utils.config.get_secret: that imports Streamlit's secrets
    machinery, which warns about a missing ScriptRunContext outside a running app.
    """
    import tomllib

    path = Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"
    if not path.exists():
        sys.exit(f"No secrets file at {path}")
    env = tomllib.load(path.open("rb")).get("DHIS2_ENV", {})
    base = (env.get("BASE_URL") or "").rstrip("/")
    if not base:
        sys.exit("DHIS2_ENV.BASE_URL is not set in .streamlit/secrets.toml")
    return base, (env.get("USERNAME", ""), env.get("PASSWORD", ""))


def _get(base, auth, path, params):
    response = requests.get(f"{base}{path}", params=params, auth=auth, timeout=60)
    response.raise_for_status()
    return response.json()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--level", type=int, default=2,
                        help="org unit hierarchy level (2 is usually district/LGA)")
    parser.add_argument("--data-elements", metavar="SUBSTRING",
                        help="list aggregate numeric data elements matching this name")
    parser.add_argument("--skeleton", action="store_true",
                        help="print a DHIS2_ORG_UNIT_MAP skeleton keyed by Borno LGA")
    args = parser.parse_args()

    base, auth = _credentials()
    print(f"instance: {base}\n")

    if args.data_elements:
        payload = _get(base, auth, "/api/dataElements", {
            "filter": ["domainType:eq:AGGREGATE", "valueType:eq:NUMBER",
                       f"name:ilike:{args.data_elements}"],
            "fields": "id,name", "paging": "false",
        })
        elements = payload.get("dataElements", [])
        print(f"{len(elements)} matching data element(s):")
        for element in elements:
            print(f"  {element['id']}  {element['name']}")
        return

    payload = _get(base, auth, "/api/organisationUnits", {
        "filter": f"level:eq:{args.level}", "fields": "id,name", "paging": "false",
    })
    units = sorted(payload.get("organisationUnits", []), key=lambda u: u["name"])
    print(f"{len(units)} org unit(s) at level {args.level}:")
    for unit in units:
        print(f"  {unit['id']}  {unit['name']}")

    if args.skeleton:
        # Keyed by the LGA names the Site Log actually records, values blank. Left blank on
        # purpose: pairing a Borno LGA with whatever org unit happens to sit at the same
        # index would be a fabricated mapping that looks deliberate.
        print("\n# Paste into .streamlit/secrets.toml, filling in UIDs from the list above:")
        print("DHIS2_ORG_UNIT_MAP = '" + json.dumps({lga: "" for lga in BORNO_LGAS}) + "'")


if __name__ == "__main__":
    main()
