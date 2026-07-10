# =========================================================================
# HISTORICAL TREND VIEW (components/forecasting.py)
#
# Previously "Seasonal Forecaster" — a SARIMAX projection built on
# simulated future weather and, when real specimen data was thin,
# simulated historical counts too. Replaced with an honest view of real
# weekly specimen trends and real historical NASA POWER weather for
# actual recorded collection coordinates. No projection into the future.
# =========================================================================
import streamlit as st

from utils.forecasting_engine import build_historical_trend
from utils.icons import render_page_header


def render_forecasting_page():
    render_page_header(
        title="Historical Trends",
        icon_name="forecaster",
        caption="Real weekly specimen trends, paired with real historical NASA POWER weather data.",
    )
    st.markdown("---")

    target_genus = st.selectbox("Genus", ["Anopheles", "Culex", "Aedes"])

    trend = build_historical_trend(target_genus)

    if not trend["available"]:
        st.warning(trend["reason"])
        return

    st.caption(f"**{trend['weeks_logged']}** week(s) of real {target_genus} data logged.")

    st.subheader(f"{target_genus} — Weekly Specimen Count")
    weekly_df = trend["weekly_counts"].set_index("week").rename(columns={"count": f"{target_genus} count"})
    st.line_chart(weekly_df, use_container_width=True)

    st.markdown("---")
    st.subheader("Historical Environmental Conditions")

    if trend["coordinates_used"]:
        lat, lon = trend["coordinates_used"]
        st.caption(f"Based on average recorded collection coordinates: {lat:.4f}, {lon:.4f}")

    if not trend["weather_available"]:
        st.info(trend["weather_reason"])
    else:
        weather_df = trend["weather"].set_index("Date")

        c1, c2, c3 = st.columns(3)
        c1.metric("Avg Temperature", f"{weather_df['Temperature'].mean():.1f}°C")
        c2.metric("Avg Humidity", f"{weather_df['Humidity'].mean():.1f}%")
        c3.metric("Total Rainfall", f"{weather_df['Rainfall'].sum():.1f}mm")

        st.line_chart(weather_df[["Temperature", "Humidity", "Rainfall"]], use_container_width=True)
        st.caption("Source: NASA POWER (power.larc.nasa.gov), historical daily data, resampled to weekly.")

    with st.expander("View underlying weekly specimen counts"):
        st.dataframe(
            trend["weekly_counts"].rename(columns={"week": "Week", "count": f"{target_genus} Count"}),
            use_container_width=True, hide_index=True,
        )
