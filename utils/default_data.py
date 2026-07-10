# =========================================================================
# DEFAULT BASELINE ENTOMOLOGICAL DATASET (utils/default_data.py)
# =========================================================================
import pandas as pd


def get_clean_default_data() -> pd.DataFrame:
    """Returns the baseline structural dataframe for local fallback operations."""
    columns = [
        "Survey_Date", "Zone_ID", "Zone_Name", "Latitude", "Longitude",
        "Base_Larval_Count", "Anopheles_Count", "Culex_Count", "Aedes_Count",
        "Breeding_Sites_Identified", "PyResistance_Detected", "OpResistance_Detected",
        "Last_Intervention_Days_Ago", "Temperature_C", "Humidity_Pct",
        "Salinity_ppt", "Water_pH", "Dissolved_Oxygen_mgL", "NDVI_Canopy",
        "owner_email", "owner_id"
    ]
    # Return an empty dataframe with correct schema structure
    return pd.DataFrame(columns=columns)
