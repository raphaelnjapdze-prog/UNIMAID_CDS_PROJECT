# =========================================================================
# NATIONAL INFORMATION SYSTEM API GATEWAY INTERFACE (utils/dhis2_client.py)
# =========================================================================
import json

import pandas as pd
import requests
import streamlit as st

from utils.logging_config import get_logger

logger = get_logger(__name__)

# Hardcoded dictionary placeholder showing how standard regional names map
# to unique UIDs inside the National DHIS2 Organisation Unit registry.
NIGERIA_NHMIS_ORG_UNITS = {
    "Maiduguri": "Hg7824kHGhd",
    "Jere": "Yt8923jHGfd",
    "Bama": "Pl6712mNBvc",
    "Biye": "Kj8934nBvcd"
}

# Unique structural Data Element UIDs mapped to the vector registry fields
VECTOR_DATA_ELEMENT_MAPPINGS = {
    "Anopheles": "uM8923hGjdf",
    "Culex": "vK7812jHfds",
    "Aedes": "wL9034kHGda",
    "Mansonia": "xM1289jHGfd",
    "Other_Genera": "zP5634kHGas"
}

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

def push_vector_payload_to_dhis2(dataframe):
    """
    Transforms canonical DataFrame shapes into an explicit JSON array mapping
    and dispatches an authorized bulk transactional POST to the NHMIS endpoint.
    """
    # 1. Fetch encrypted pipeline credentials from environment parameters
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
    data_values_payload = []

    # 2. Iteratively parse DataFrame layout rows into explicit dataValue definitions
    for idx, row in dataframe.iterrows():
        lga_name = row.get("LGA_District", "")
        org_unit_uid = NIGERIA_NHMIS_ORG_UNITS.get(lga_name, None)

        # Skip row processing loops if the locality can't be mapped to an authorized organizational node
        if not org_unit_uid:
            continue

        period_string = convert_date_to_dhis2_period(row.get("Collection_Date", ""))

        # Determine target fallback tracking vector column keys
        anoph_key = "Anopheles" if "Anopheles" in dataframe.columns else "Anopheles_Count"
        culex_key = "Culex" if "Culex" in dataframe.columns else "Culex_Count"
        aedes_key = "Aedes" if "Aedes" in dataframe.columns else "Aedes_Count"
        mansonia_key = "Mansonia" if "Mansonia" in dataframe.columns else "Mansonia_Count"
        other_key = "Other_Genera" if "Other_Genera" in dataframe.columns else "Other_Genera_Count"

        # Bundle structural genus metrics counts iteratively
        genus_metrics = {
            "Anopheles": row.get(anoph_key, 0),
            "Culex": row.get(culex_key, 0),
            "Aedes": row.get(aedes_key, 0),
            "Mansonia": row.get(mansonia_key, 0),
            "Other_Genera": row.get(other_key, 0)
        }

        for genus_name, counts in genus_metrics.items():
            element_uid = VECTOR_DATA_ELEMENT_MAPPINGS.get(genus_name)
            if element_uid and pd.notna(counts):
                data_values_payload.append({
                    "dataElement": element_uid,
                    "period": period_string,
                    "orgUnit": org_unit_uid,
                    "value": str(int(counts))
                })

    if not data_values_payload:
        return {
            "status": "WARNING",
            "message": "Zero records compiled. Verify that your field survey LGA parameters perfectly match standard organizational registries."
        }

    # 3. Encapsulate array inside standard DHIS2 JSON parent object
    master_payload = {"dataValues": data_values_payload}

    # 4. Execute programmatic transmission handshake
    try:
        response = requests.post(
            url=target_endpoint,
            headers={"Content-Type": "application/json"},
            auth=(username, password),
            data=json.dumps(master_payload),
            timeout=35
        )

        if response.status_code in [200, 201]:
            # Retain statistical output responses (imported, updated, ignored logs)
            return {
                "status": "SUCCESS",
                "response_json": response.json()
            }
        else:
            return {
                "status": "FAILURE",
                "message": f"Server rejected submission pipeline with HTTP Error Code: {response.status_code}",
                "details": response.text
            }

    except requests.exceptions.Timeout:
        return {"status": "ERROR", "message": "The remote national health database handshake execution timed out."}
    except Exception as err:
        return {"status": "ERROR", "message": f"Fatal network socket disconnection: {str(err)}"}
