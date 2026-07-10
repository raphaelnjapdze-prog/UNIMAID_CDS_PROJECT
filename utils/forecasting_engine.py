# =========================================================================
# HISTORICAL TREND ENGINE (utils/forecasting_engine.py)
#
# Previously fit a SARIMAX model to forecast future vector counts. Removed
# entirely: it required (1) simulated future weather, since NASA POWER is
# historical/reanalysis data and cannot supply real future values, and
# (2) a historical vector-count series that — whenever real data was thin
# (len(df) < 10) — was itself randomly generated, meaning most forecasts
# produced by this engine were fit on fabricated numbers from end to end.
#
# Replaced with a real trend view: actual weekly specimen genus counts
# from specimen_records, paired with real historical NASA POWER weather
# for the actual GPS coordinates on record — no synthetic substitute for
# either half.
# =========================================================================
import pandas as pd

from utils.data_manager import extract_genus_counts_from_screening, load_specimen_records
from utils.weather_engine import fetch_nasa_power_environmental_data

MIN_WEEKS_FOR_TREND = 3  # minimum real weeks of specimen data before showing a trend chart


def _weekly_genus_series(df: pd.DataFrame, target_genus: str) -> pd.DataFrame:
    """Real weekly counts for one genus, derived from specimen_records."""
    if df.empty:
        return pd.DataFrame(columns=["week", "count"])

    working = df.copy()
    working["collection_date"] = pd.to_datetime(working.get("collection_date"), errors="coerce")
    working = working.dropna(subset=["collection_date"])
    if working.empty:
        return pd.DataFrame(columns=["week", "count"])

    counts = []
    for _, row in working.iterrows():
        genus_counts = extract_genus_counts_from_screening(row.get("field_screening_result"))
        counts.append(genus_counts.get(target_genus, 0))

    working["count"] = counts
    working["week"] = working["collection_date"].dt.to_period("W").dt.start_time
    return working.groupby("week")["count"].sum().reset_index()


def _representative_coordinates(df: pd.DataFrame) -> tuple[float, float] | None:
    """
    Real average GPS coordinates from specimen_records, rather than a
    hardcoded default location. Returns None if no coordinates are on file.
    """
    if df.empty or "gps_lat" not in df.columns or "gps_lon" not in df.columns:
        return None
    coords = df.dropna(subset=["gps_lat", "gps_lon"])
    if coords.empty:
        return None
    return float(coords["gps_lat"].mean()), float(coords["gps_lon"].mean())


def build_historical_trend(target_genus: str = "Anopheles") -> dict:
    """
    Returns:
    {
        "available": bool,
        "reason": str,
        "weekly_counts": DataFrame | None,   # columns: week, count
        "weeks_logged": int,
        "weather": DataFrame | None,          # columns: Date, Temperature, Humidity, Rainfall
        "weather_available": bool,
        "weather_reason": str,
        "coordinates_used": (lat, lon) | None,
    }
    """
    specimen_df = load_specimen_records()
    weekly = _weekly_genus_series(specimen_df, target_genus)

    result = {
        "available": False,
        "reason": "",
        "weekly_counts": weekly if not weekly.empty else None,
        "weeks_logged": len(weekly),
        "weather": None,
        "weather_available": False,
        "weather_reason": "",
        "coordinates_used": None,
    }

    if weekly.empty:
        result["reason"] = "No specimen records with valid collection dates yet."
        return result

    if len(weekly) < MIN_WEEKS_FOR_TREND:
        result["reason"] = (
            f"Only {len(weekly)} week(s) of {target_genus} data logged — "
            f"need at least {MIN_WEEKS_FOR_TREND} weeks for a meaningful trend view. "
            "Keep logging specimens via Site Log Entry or Diagnostics."
        )
        return result

    result["available"] = True

    coords = _representative_coordinates(specimen_df)
    if coords is None:
        result["weather_reason"] = "No GPS coordinates recorded on any specimen yet — weather data unavailable."
        return result

    lat, lon = coords
    result["coordinates_used"] = (lat, lon)

    start_date = weekly["week"].min()
    end_date = weekly["week"].max()

    weather_df = fetch_nasa_power_environmental_data(lat, lon, start_date, end_date)
    if weather_df is None:
        result["weather_reason"] = (
            "Could not retrieve NASA POWER weather data (API unavailable or no "
            "response) — showing specimen trend only."
        )
        return result

    result["weather"] = weather_df
    result["weather_available"] = True
    return result
