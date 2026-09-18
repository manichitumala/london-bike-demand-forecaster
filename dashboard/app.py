"""Streamlit dashboard: London bike-hire demand forecast.

Reads the parquet files produced by `bikeforecast.models.forecast` — it does
not run the pipeline itself. Run `python -m bikeforecast.pipeline` first (or
let the scheduled GitHub Action refresh the data).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bikeforecast.config import ROOT

PROCESSED_DIR = ROOT / "data" / "processed"

# dataviz reference palette (references/palette.md) — status + categorical slots
COLOR_GOOD = "#0ca30c"
COLOR_WARNING = "#fab219"
COLOR_CRITICAL = "#d03b3b"
COLOR_BLUE = "#2a78d6"
COLOR_ORANGE = "#eb6834"
COLOR_MUTED = "#898781"
COLOR_GRID = "#e1e0d9"

st.set_page_config(page_title="London Bike-Hire Demand Forecast", layout="wide")


@st.cache_data(ttl=3600)
def load_data():
    forecast = pd.read_parquet(PROCESSED_DIR / "forecast.parquet")
    risk = pd.read_parquet(PROCESSED_DIR / "station_risk.parquet")
    return forecast, risk


def risk_color(score: float) -> list[int]:
    if score >= 0.15:
        hex_c = COLOR_CRITICAL
    elif score >= 0.03:
        hex_c = COLOR_WARNING
    else:
        hex_c = COLOR_GOOD
    hex_c = hex_c.lstrip("#")
    return [int(hex_c[i : i + 2], 16) for i in (0, 2, 4)] + [200]


def main() -> None:
    st.title("London Bike-Hire Demand Forecast")
    st.caption(
        "7-day hourly demand forecast per Santander Cycles docking station, "
        "built from TfL journey history + Open-Meteo weather. "
        "LightGBM vs. seasonal-naive baseline — see reports/evaluation.json."
    )

    try:
        forecast, risk = load_data()
    except FileNotFoundError:
        st.error(
            "No forecast data found. Run `python -m bikeforecast.pipeline` "
            "to ingest data and generate a forecast first."
        )
        return

    horizon_start = forecast["hour_ts"].min()
    horizon_end = forecast["hour_ts"].max()
    st.caption(f"Forecast horizon: {horizon_start:%d %b %Y} – {horizon_end:%d %b %Y}")

    tab_map, tab_station, tab_risk = st.tabs(
        ["Station map", "7-day station forecast", "Stations likely to run empty"]
    )

    with tab_map:
        st.subheader("All stations — 7-day empty-dock risk")
        st.caption(
            "Colour = share of the next 168 hours a station's simulated stock is "
            "at or below 2 bikes. Simulation starts each station at 50% capacity "
            "(no historical stock data is published) — read this as relative risk, "
            "not a calibrated probability."
        )
        map_df = risk.dropna(subset=["lat", "lon"]).copy()
        map_df["color"] = map_df["risk_score"].apply(risk_color)
        map_df["radius"] = 40 + map_df["risk_score"] * 200

        view_state = pdk.ViewState(
            latitude=float(map_df["lat"].median()),
            longitude=float(map_df["lon"].median()),
            zoom=11,
            pitch=0,
        )
        layer = pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            get_position="[lon, lat]",
            get_fill_color="color",
            get_radius="radius",
            pickable=True,
        )
        tooltip = {
            "html": "<b>{station_name}</b><br/>Risk score: {risk_score}<br/>"
            "Low-dock hours (of 168): {low_risk_hours}<br/>Capacity: {capacity}",
        }
        st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip))

        legend_cols = st.columns(3)
        legend_cols[0].markdown(f"🟢 **OK** — risk < 3%")
        legend_cols[1].markdown(f"🟠 **Watch** — 3–15%")
        legend_cols[2].markdown(f"🔴 **Critical** — ≥ 15%")

    with tab_station:
        st.subheader("Per-station 7-day forecast")
        station_options = risk.sort_values("station_name")[["station_id", "station_name"]]
        label_map = dict(zip(station_options["station_id"], station_options["station_name"]))
        chosen = st.selectbox(
            "Station",
            options=station_options["station_id"],
            format_func=lambda sid: label_map.get(sid, str(sid)),
        )

        sdf = forecast[forecast["station_id"] == chosen].sort_values("hour_ts")
        capacity = sdf["capacity"].iloc[0] if len(sdf) else None

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=sdf["hour_ts"], y=sdf["pred_departures"],
                name="Predicted departures", line=dict(color=COLOR_ORANGE, width=2),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=sdf["hour_ts"], y=sdf["pred_arrivals"],
                name="Predicted arrivals", line=dict(color=COLOR_BLUE, width=2),
            )
        )
        fig.update_layout(
            height=320,
            margin=dict(t=10, b=10, l=10, r=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            xaxis=dict(gridcolor=COLOR_GRID),
            yaxis=dict(title="Bikes / hour", gridcolor=COLOR_GRID),
            plot_bgcolor="#fcfcfb",
            paper_bgcolor="#fcfcfb",
        )
        st.plotly_chart(fig, width='stretch')

        stock_fig = go.Figure()
        stock_fig.add_trace(
            go.Scatter(
                x=sdf["hour_ts"], y=sdf["pred_stock"],
                name="Simulated dock stock", line=dict(color=COLOR_BLUE, width=2),
                fill="tozeroy", fillcolor="rgba(42,120,214,0.12)",
            )
        )
        stock_fig.add_hline(y=2, line_dash="dash", line_color=COLOR_CRITICAL,
                             annotation_text="Empty-dock threshold")
        if capacity and pd.notna(capacity):
            stock_fig.add_hline(y=capacity, line_dash="dot", line_color=COLOR_MUTED,
                                 annotation_text="Capacity")
        stock_fig.update_layout(
            height=280,
            margin=dict(t=10, b=10, l=10, r=10),
            xaxis=dict(gridcolor=COLOR_GRID),
            yaxis=dict(title="Simulated bikes on stand", gridcolor=COLOR_GRID),
            plot_bgcolor="#fcfcfb",
            paper_bgcolor="#fcfcfb",
            showlegend=False,
        )
        st.caption("Simulated stock (50%-capacity start + predicted arrivals − departures)")
        st.plotly_chart(stock_fig, width='stretch')

    with tab_risk:
        st.subheader("Stations most likely to run empty this week")
        top_n = st.slider("Show top N stations", 5, 50, 20)
        top = risk.sort_values("risk_score", ascending=False).head(top_n)
        bar = go.Figure(
            go.Bar(
                x=top["risk_score"],
                y=top["station_name"],
                orientation="h",
                marker_color=[
                    COLOR_CRITICAL if r >= 0.15 else COLOR_WARNING if r >= 0.03 else COLOR_GOOD
                    for r in top["risk_score"]
                ],
            )
        )
        bar.update_layout(
            height=max(320, 24 * len(top)),
            margin=dict(t=10, b=10, l=10, r=10),
            xaxis=dict(title="Share of next 168h at/below 2 bikes", tickformat=".0%", gridcolor=COLOR_GRID),
            yaxis=dict(autorange="reversed"),
            plot_bgcolor="#fcfcfb",
            paper_bgcolor="#fcfcfb",
        )
        st.plotly_chart(bar, width='stretch')
        st.dataframe(
            top[["station_name", "risk_score", "low_risk_hours", "capacity", "avg_pred_departures"]]
            .rename(columns={
                "station_name": "Station",
                "risk_score": "Risk score",
                "low_risk_hours": "Low-dock hours (of 168)",
                "capacity": "Capacity",
                "avg_pred_departures": "Avg predicted departures/hr",
            }),
            width='stretch',
            hide_index=True,
        )


if __name__ == "__main__":
    main()
