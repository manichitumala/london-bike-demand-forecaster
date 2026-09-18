"""Produce the deployable 7-day-ahead forecast used by the dashboard.

Retrains both LightGBM models on *all* actual history (train.py's held-out
test window was only for evaluation), predicts departures & arrivals for
every station over the next 168 hours, then simulates each station's dock
occupancy forward from a neutral starting point to flag hours it's likely
to run empty.

Docking-level stock history isn't published anywhere (TfL/BikePoint only
expose the *current* live occupancy, not a historical time series), so the
simulation starts every station at 50% of its capacity rather than a real
observed count — see README limitations. Treat the "likely to run empty"
flag as relative risk ranking, not a calibrated probability.
"""
from __future__ import annotations

import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bikeforecast.config import DB_PATH, ROOT
from bikeforecast.models.dataset import attach_profile, build_seasonal_profile, feature_cols, load_features

PROCESSED_DIR = ROOT / "data" / "processed"
DEFAULT_CAPACITY = 20
LOW_DOCK_THRESHOLD = 2  # bikes remaining at/below this counts as "likely to run empty"


def fit_final_model(actual: pd.DataFrame, target: str) -> tuple[lgb.LGBMRegressor, pd.DataFrame]:
    lag_col = "lag_168h_departures" if target == "departures" else "lag_168h_arrivals"
    usable = actual.dropna(subset=[lag_col]).copy()
    profile = build_seasonal_profile(usable, target)
    usable = attach_profile(usable, profile, target)

    cols = feature_cols(target)
    model = lgb.LGBMRegressor(
        objective="regression",
        metric="mae",
        n_estimators=400,
        learning_rate=0.05,
        num_leaves=63,
        min_child_samples=30,
        random_state=42,
        verbosity=-1,
    )
    model.fit(usable[cols], usable[target], categorical_feature=["station_id"])
    return model, profile


def simulate_stock(group: pd.DataFrame, capacity: float) -> pd.Series:
    cap = capacity if pd.notna(capacity) and capacity > 0 else DEFAULT_CAPACITY
    stock = cap / 2.0
    levels = []
    for arr, dep in zip(group["pred_arrivals"], group["pred_departures"]):
        stock = float(np.clip(stock + arr - dep, 0, cap))
        levels.append(stock)
    return pd.Series(levels, index=group.index)


def main() -> None:
    df = load_features()
    actual = df[df["is_actual"]].copy()
    horizon = df[~df["is_actual"]].copy()

    preds = horizon[["station_id", "hour_ts", "hour_of_day", "day_of_week"]].copy()
    for target in ("departures", "arrivals"):
        model, profile = fit_final_model(actual, target)
        h = attach_profile(horizon, profile, target)
        cols = feature_cols(target)
        preds[f"pred_{target}"] = model.predict(h[cols]).clip(min=0)

    import duckdb

    con = duckdb.connect(str(DB_PATH), read_only=True)
    stations = con.execute(
        "SELECT station_id, station_name, lat, lon, capacity FROM dim_stations"
    ).fetchdf()
    con.close()

    preds = preds.merge(stations, on="station_id", how="left").sort_values(["station_id", "hour_ts"])
    preds["pred_stock"] = preds.groupby("station_id", group_keys=False).apply(
        lambda g: simulate_stock(g, g["capacity"].iloc[0])
    )
    preds["is_low_risk_hour"] = preds["pred_stock"] <= LOW_DOCK_THRESHOLD

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    preds.to_parquet(PROCESSED_DIR / "forecast.parquet", index=False)

    risk = (
        preds.groupby(["station_id", "station_name", "lat", "lon", "capacity"], observed=True, dropna=False)
        .agg(
            low_risk_hours=("is_low_risk_hour", "sum"),
            total_hours=("is_low_risk_hour", "size"),
            avg_pred_departures=("pred_departures", "mean"),
            min_pred_stock=("pred_stock", "min"),
        )
        .reset_index()
    )
    risk["risk_score"] = risk["low_risk_hours"] / risk["total_hours"]
    risk = risk.sort_values("risk_score", ascending=False)
    risk.to_parquet(PROCESSED_DIR / "station_risk.parquet", index=False)

    print(f"Forecast: {len(preds)} rows -> {PROCESSED_DIR / 'forecast.parquet'}")
    print(f"Station risk summary: {len(risk)} rows -> {PROCESSED_DIR / 'station_risk.parquet'}")
    print(f"Horizon: {preds['hour_ts'].min()} .. {preds['hour_ts'].max()}")
    print(f"Stations flagged with >0 low-dock hours: {(risk['low_risk_hours'] > 0).sum()}")


if __name__ == "__main__":
    main()
