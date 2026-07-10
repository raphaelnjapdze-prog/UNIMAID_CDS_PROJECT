# Rebuilt around two independent real sources: specimen_records (larval/
# genus density) and clinical_case_data (real confirmed case counts,
# manually logged per facility per period). If either source lacks enough
# real, overlapping data, this returns an honest "not available" state —
# never a simulated substitute.
# =========================================================================
import numpy as np
import pandas as pd

from utils.data_manager import extract_genus_counts_from_screening, load_clinical_case_data, load_specimen_records

MIN_OVERLAPPING_PERIODS = 5  # minimum weeks with both larval and case data to attempt a correlation


def _weekly_larval_density(specimen_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregates specimen_records into a weekly larval/genus density series.
    'Density' here is total specimens logged per week — a real, directly
    measured count, not an estimated rate per dip (that would require
    dip-effort data this schema doesn't capture).
    """
    if specimen_df.empty:
        return pd.DataFrame(columns=["week", "total_density"])

    df = specimen_df.copy()
    df["collection_date"] = pd.to_datetime(df.get("collection_date"), errors="coerce")
    df = df.dropna(subset=["collection_date"])
    if df.empty:
        return pd.DataFrame(columns=["week", "total_density"])

    weekly_rows = []
    for _, row in df.iterrows():
        counts = extract_genus_counts_from_screening(row.get("field_screening_result"))
        total = sum(counts.values())
        weekly_rows.append({"collection_date": row["collection_date"], "total_density": total})

    weekly_df = pd.DataFrame(weekly_rows)
    weekly_df["week"] = weekly_df["collection_date"].dt.to_period("W").dt.start_time
    return weekly_df.groupby("week")["total_density"].sum().reset_index()


def _weekly_case_counts(case_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregates clinical_case_data into a weekly confirmed-case series."""
    if case_df.empty:
        return pd.DataFrame(columns=["week", "confirmed_cases"])

    df = case_df.copy()
    df["report_date"] = pd.to_datetime(df.get("report_date"), errors="coerce")
    df = df.dropna(subset=["report_date"])
    if df.empty:
        return pd.DataFrame(columns=["week", "confirmed_cases"])

    df["week"] = df["report_date"].dt.to_period("W").dt.start_time
    return df.groupby("week")["confirmed_cases"].sum().reset_index()


def build_case_matrix() -> dict:
    """
    Returns a dict describing data availability plus the merged weekly
    matrix when enough real, overlapping data exists.

    {
        "available": bool,
        "reason": str,                 # populated when available is False
        "matrix": DataFrame | None,     # columns: week, total_density, confirmed_cases
        "larval_weeks": int,
        "case_weeks": int,
        "overlapping_weeks": int,
    }
    """
    specimen_df = load_specimen_records()
    case_df = load_clinical_case_data()

    larval_weekly = _weekly_larval_density(specimen_df)
    case_weekly = _weekly_case_counts(case_df)

    if larval_weekly.empty:
        return {
            "available": False,
            "reason": "No specimen records with valid collection dates yet.",
            "matrix": None, "larval_weeks": 0, "case_weeks": len(case_weekly), "overlapping_weeks": 0,
        }
    if case_weekly.empty:
        return {
            "available": False,
            "reason": "No clinical case data submitted yet. Use Clinical Case Data Entry to log real case counts.",
            "matrix": None, "larval_weeks": len(larval_weekly), "case_weeks": 0, "overlapping_weeks": 0,
        }

    merged = pd.merge(larval_weekly, case_weekly, on="week", how="inner").sort_values("week")

    if len(merged) < MIN_OVERLAPPING_PERIODS:
        return {
            "available": False,
            "reason": (
                f"Only {len(merged)} week(s) have both larval and case data recorded — "
                f"need at least {MIN_OVERLAPPING_PERIODS} overlapping weeks for a meaningful correlation. "
                "Keep logging both specimen collections and clinical case data for the same periods."
            ),
            "matrix": merged, "larval_weeks": len(larval_weekly), "case_weeks": len(case_weekly),
            "overlapping_weeks": len(merged),
        }

    return {
        "available": True,
        "reason": "",
        "matrix": merged,
        "larval_weeks": len(larval_weekly),
        "case_weeks": len(case_weekly),
        "overlapping_weeks": len(merged),
    }


def compute_lagged_correlation(matrix: pd.DataFrame, weeks_lag: int = 0) -> dict:
    """
    Shifts larval density forward by weeks_lag relative to case counts and
    computes a real Pearson correlation. Returns an honest 'insufficient
    data' result if too few points remain after the shift — never a
    fabricated fallback number.
    """
    working = matrix.copy()
    working["shifted_density"] = working["total_density"].shift(weeks_lag)
    analysis_set = working.dropna(subset=["shifted_density", "confirmed_cases"])

    if len(analysis_set) < MIN_OVERLAPPING_PERIODS:
        return {
            "available": False,
            "reason": f"Only {len(analysis_set)} data point(s) remain after applying a {weeks_lag}-week lag.",
            "r": None, "r_squared": None, "slope": None, "intercept": None, "analysis_set": None,
        }

    r = analysis_set["shifted_density"].corr(analysis_set["confirmed_cases"])
    if pd.isna(r):
        return {
            "available": False,
            "reason": "Correlation could not be computed (no variance in one of the series).",
            "r": None, "r_squared": None, "slope": None, "intercept": None, "analysis_set": None,
        }

    slope, intercept = np.polyfit(analysis_set["shifted_density"], analysis_set["confirmed_cases"], 1)

    return {
        "available": True,
        "reason": "",
        "r": round(r, 3),
        "r_squared": round(r ** 2, 3),
        "slope": slope,
        "intercept": intercept,
        "analysis_set": analysis_set,
    }


def find_best_lag(matrix: pd.DataFrame, max_lag_weeks: int = 6) -> dict:
    """
    Tries lags 0..max_lag_weeks and returns the one with the strongest real
    correlation. All results are genuinely computed — no lag is favored
    except by actual r² value.
    """
    results = {}
    for lag in range(0, max_lag_weeks + 1):
        results[lag] = compute_lagged_correlation(matrix, weeks_lag=lag)

    valid = {lag: r for lag, r in results.items() if r["available"]}
    if not valid:
        return {"available": False, "reason": "No lag produced a computable correlation with current data.", "best_lag": None, "all_results": results}

    best_lag = max(valid, key=lambda lag: valid[lag]["r_squared"])
    return {"available": True, "reason": "", "best_lag": best_lag, "best_result": valid[best_lag], "all_results": results}
