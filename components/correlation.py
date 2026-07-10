# =========================================================================
# LARVAL DENSITY vs. CLINICAL CASE CORRELATION (components/correlation.py)
#
# Previously plotted a fabricated dataset (sine-wave fallback, or clinical
# cases derived as larval_density * 4.2) and always showed a "strong
# correlation" regardless of whether real data existed. Rebuilt around
# utils.epidemiology_engine's honest data-availability checks — this page
# now either shows a real, defensible correlation, or clearly states why
# one isn't available yet and what's needed to get there.
# =========================================================================
import numpy as np
import streamlit as st

from utils.epidemiology_engine import build_case_matrix, compute_lagged_correlation, find_best_lag
from utils.icons import render_page_header


def render_correlation_page():
    render_page_header(
        title="Clinical Case Correlation",
        icon_name="correlation",
        caption="Real correlation between logged larval density and confirmed clinical malaria cases.",
    )
    st.markdown("---")

    status = build_case_matrix()

    st.caption(
        f"Data on hand: **{status['larval_weeks']}** week(s) of specimen data, "
        f"**{status['case_weeks']}** week(s) of clinical case data, "
        f"**{status['overlapping_weeks']}** overlapping week(s)."
    )

    if not status["available"]:
        st.warning(status["reason"])
        st.info(
            "This page requires real data from two places: **Site Log Entry / "
            "Diagnostics** (specimen counts) and **Clinical Case Data Entry** "
            "(confirmed malaria cases), covering at least 5 of the same weeks, "
            "before a correlation can be honestly computed."
        )
        if status["matrix"] is not None and not status["matrix"].empty:
            with st.expander("View the overlapping data collected so far"):
                st.dataframe(
                    status["matrix"].rename(columns={
                        "week": "Week", "total_density": "Total Specimens Logged",
                        "confirmed_cases": "Confirmed Cases",
                    }),
                    use_container_width=True, hide_index=True,
                )
        return

    matrix = status["matrix"]

    st.subheader("Lag Selection")
    lag_mode = st.radio(
        "Lag approach",
        ["Manual — choose weeks of lag", "Automatic — find the best-fitting lag"],
        horizontal=True,
    )

    max_lag = min(6, len(matrix) - 1) if len(matrix) > 1 else 0

    if lag_mode == "Automatic — find the best-fitting lag":
        best = find_best_lag(matrix, max_lag_weeks=max_lag)
        if not best["available"]:
            st.warning(best["reason"])
            return
        weeks_lag = best["best_lag"]
        result = best["best_result"]
        st.caption(f"Automatically selected lag: **{weeks_lag} week(s)** — highest r² among lags tested (0–{max_lag}).")
    else:
        weeks_lag = st.slider("Weeks of lag (larval density shifted forward)", min_value=0, max_value=max_lag, value=0)
        result = compute_lagged_correlation(matrix, weeks_lag=weeks_lag)
        if not result["available"]:
            st.warning(result["reason"])
            return

    r_val = result["r"]
    r_sq = result["r_squared"]
    slope = result["slope"]
    intercept = result["intercept"]
    analysis_set = result["analysis_set"]

    # ── Metric cards ──────────────────────────────────────────────────────
    strength = "Weak" if abs(r_val) < 0.4 else "Moderate" if abs(r_val) < 0.7 else "Strong"
    m1, m2, m3 = st.columns(3)
    m1.metric("Pearson r", f"{r_val:.3f}", strength)
    m2.metric("R² (variance explained)", f"{r_sq:.1%}")
    m3.metric("Slope", f"{slope:.3f}", "cases per unit specimen count")

    st.caption(
        f"Based on **{len(analysis_set)}** overlapping week(s) of real data at a "
        f"{weeks_lag}-week lag. This is a correlational, not causal, relationship — "
        "confounders (reporting completeness, other interventions, seasonality) "
        "are not controlled for."
    )

    st.markdown("---")

    tab1, tab2 = st.tabs(["Time Series", "Scatter & Regression"])

    with tab1:
        st.subheader("Specimen Density vs. Confirmed Cases Over Time")
        timeline_df = matrix.set_index("week")[["total_density", "confirmed_cases"]].rename(columns={
            "total_density": "Specimens Logged", "confirmed_cases": "Confirmed Cases",
        })
        st.line_chart(timeline_df, use_container_width=True)

    with tab2:
        st.subheader(f"Shifted Density (+{weeks_lag}w) vs. Confirmed Cases")
        scatter_df = analysis_set.rename(columns={
            "shifted_density": "Shifted Specimen Density", "confirmed_cases": "Confirmed Cases",
        })
        st.scatter_chart(scatter_df, x="Shifted Specimen Density", y="Confirmed Cases", use_container_width=True)

        x_range = np.linspace(scatter_df["Shifted Specimen Density"].min(), scatter_df["Shifted Specimen Density"].max(), 20)
        st.caption(
            f"Fitted line: cases ≈ {slope:.3f} × specimens + {intercept:.2f} "
            f"(range: {x_range.min():.1f}–{x_range.max():.1f} specimens/week)"
        )

    st.markdown("---")
    st.subheader("Interpretation")

    if r_sq < 0.3:
        st.info(
            f"At a {weeks_lag}-week lag, specimen density explains only "
            f"{r_sq:.0%} of the variance in confirmed cases (r = {r_val:.2f}). "
            "This is a weak relationship — try other lag values, or note that "
            "more overlapping weeks of data will make this estimate more reliable."
        )
    elif r_val > 0:
        st.success(
            f"At a {weeks_lag}-week lag, there is a positive relationship "
            f"(r = {r_val:.2f}, R² = {r_sq:.0%}) between specimen density and "
            "confirmed cases in the data logged so far. Treat this as a working "
            "hypothesis to monitor, not a confirmed causal finding — more weeks "
            "of paired data will sharpen or revise this estimate."
        )
    else:
        st.warning(
            f"At a {weeks_lag}-week lag, the relationship is negative "
            f"(r = {r_val:.2f}) — cases decrease as specimen density increases. "
            "This may reflect confounding factors or insufficient data; consider "
            "trying other lags or accumulating more weeks of paired data."
        )

    with st.expander("View underlying weekly matrix"):
        st.dataframe(
            analysis_set.rename(columns={
                "week": "Week", "total_density": "Specimen Density",
                "shifted_density": f"Shifted Density (+{weeks_lag}w)",
                "confirmed_cases": "Confirmed Cases",
            }),
            use_container_width=True, hide_index=True,
        )
