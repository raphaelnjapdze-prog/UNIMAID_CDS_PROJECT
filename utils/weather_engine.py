# =========================================================================
# NASA POWER CLIMATE DATA INGESTION (utils/weather_engine.py)
#
# fetch_nasa_power_environmental_data() is genuine — a real call to the
# public NASA POWER API, correctly parsed. Kept as-is.
#
# generate_synthetic_weather_baseline() has been removed. It used a fixed
# random seed (np.random.seed(42)), meaning it silently produced the exact
# same fake weather sequence every time, with no way to distinguish it
# from real data by inspection. If the real API call fails, callers must
# show an honest error/empty state — never a fabricated substitute.
# =========================================================================
import pandas as pd
import requests

from utils.logging_config import get_logger

logger = get_logger(__name__)


def fetch_nasa_power_environmental_data(lat, lon, start_date, end_date) -> pd.DataFrame | None:
    """
    Queries the NASA POWER API for environmental drivers relevant to vector
    ecology:
      - T2M: Temperature at 2 Meters (°C)
      - RH2M: Relative Humidity at 2 Meters (%)
      - PRECTOTCORR: Corrected Total Precipitation (mm/day)

    Returns None on any failure — caller must show an honest message,
    not a fabricated fallback dataset.
    """
    fmt_start = start_date.strftime("%Y%m%d")
    fmt_end = end_date.strftime("%Y%m%d")

    url = "https://power.larc.nasa.gov/api/temporal/daily/point"
    params = {
        "parameters": "T2M,RH2M,PRECTOTCORR",
        "community": "AG",
        "longitude": float(lon),
        "latitude": float(lat),
        "start": fmt_start,
        "end": fmt_end,
        "format": "JSON",
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code != 200:
            return None

        properties = response.json().get("properties", {})
        parameter_data = properties.get("parameter", {})

        df_dict = {
            "Temperature": parameter_data.get("T2M", {}),
            "Humidity": parameter_data.get("RH2M", {}),
            "Rainfall": parameter_data.get("PRECTOTCORR", {}),
        }
        weather_df = pd.DataFrame(df_dict)
        if weather_df.empty:
            return None

        weather_df.index = pd.to_datetime(weather_df.index, format="%Y%m%d")
        return weather_df.reset_index().rename(columns={"index": "Date"})

    except Exception:
        logger.warning("NASA POWER environmental data fetch failed", exc_info=True)
        return None
