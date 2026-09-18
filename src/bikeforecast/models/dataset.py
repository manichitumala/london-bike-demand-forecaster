"""Shared feature prep for the baseline and LightGBM models.

Deliberately excludes 1h/24h lags and a live rolling average: this project
forecasts a full 7-day horizon in one batch, so at forecast time the model
only ever has actuals up to "now" (the origin), never the hours in between
now and the target hour. The only lag that's *always* real 168h out is
exactly-a-week-ago (lag_168h). Everything else knowable at forecast time is
either calendar, forecast weather, or a station's historical (station, hour,
day-of-week) seasonal profile — computed once from data strictly before the
forecast origin, so it can't leak future information.
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bikeforecast.config import DB_PATH

TARGETS = ["departures", "arrivals"]

BASE_FEATURE_COLS = [
    "hour_of_day",
    "day_of_week",
    "is_weekend",
    "is_bank_holiday",
    "temperature_2m",
    "precipitation",
    "rain",
    "wind_speed_10m",
    "relative_humidity_2m",
]

CATEGORICAL_COLS = ["station_id"]


def load_features(db_path: Path = DB_PATH) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df = con.execute(
            """
            SELECT station_id, hour_ts, is_actual, departures, arrivals,
                   hour_of_day, day_of_week, is_weekend, is_bank_holiday,
                   temperature_2m, precipitation, rain, wind_speed_10m,
                   relative_humidity_2m,
                   lag_168h_departures, lag_168h_arrivals
            FROM fct_features
            ORDER BY station_id, hour_ts
            """
        ).fetchdf()
    finally:
        con.close()
    df["station_id"] = df["station_id"].astype("category")
    return df


def build_seasonal_profile(train_df: pd.DataFrame, target: str) -> pd.DataFrame:
    """Mean `target` per (station, hour_of_day, day_of_week), from train rows only."""
    profile = (
        train_df.groupby(["station_id", "hour_of_day", "day_of_week"], observed=True)[target]
        .mean()
        .rename(f"profile_avg_{target}")
        .reset_index()
    )
    return profile


def attach_profile(df: pd.DataFrame, profile: pd.DataFrame, target: str) -> pd.DataFrame:
    out = df.merge(profile, on=["station_id", "hour_of_day", "day_of_week"], how="left")
    global_mean = profile[f"profile_avg_{target}"].mean()
    out[f"profile_avg_{target}"] = out[f"profile_avg_{target}"].fillna(global_mean)
    return out


def feature_cols(target: str) -> list[str]:
    lag_col = "lag_168h_departures" if target == "departures" else "lag_168h_arrivals"
    return BASE_FEATURE_COLS + [lag_col, f"profile_avg_{target}"] + CATEGORICAL_COLS
