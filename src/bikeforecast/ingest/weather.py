"""Pull hourly London weather from Open-Meteo: historical archive + forward forecast.

Open-Meteo needs no API key. Historical data comes from the reanalysis
archive endpoint; the forecast endpoint additionally returns `past_days` so
the two overlap by design and we can stitch them into one continuous series.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bikeforecast.config import (
    LONDON_LAT,
    LONDON_LON,
    OPEN_METEO_ARCHIVE_URL,
    OPEN_METEO_FORECAST_URL,
    RAW_WEATHER_DIR,
    TIMEZONE,
    WEATHER_HOURLY_VARS,
)

HISTORICAL_PATH = RAW_WEATHER_DIR / "historical.parquet"
FORECAST_PATH = RAW_WEATHER_DIR / "forecast.parquet"


def _hourly_to_frame(payload: dict) -> pd.DataFrame:
    hourly = payload["hourly"]
    df = pd.DataFrame(hourly)
    df["time"] = pd.to_datetime(df["time"])
    return df.rename(columns={"time": "ts"})


def fetch_historical(start: date, end: date) -> pd.DataFrame:
    params = {
        "latitude": LONDON_LAT,
        "longitude": LONDON_LON,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": WEATHER_HOURLY_VARS,
        "timezone": TIMEZONE,
    }
    resp = requests.get(OPEN_METEO_ARCHIVE_URL, params=params, timeout=60)
    resp.raise_for_status()
    return _hourly_to_frame(resp.json())


def fetch_forecast(days_ahead: int = 7, past_days: int = 3) -> pd.DataFrame:
    params = {
        "latitude": LONDON_LAT,
        "longitude": LONDON_LON,
        "hourly": WEATHER_HOURLY_VARS,
        "forecast_days": days_ahead,
        "past_days": past_days,
        "timezone": TIMEZONE,
    }
    resp = requests.get(OPEN_METEO_FORECAST_URL, params=params, timeout=60)
    resp.raise_for_status()
    return _hourly_to_frame(resp.json())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=str, help="YYYY-MM-DD, defaults to 400 days ago")
    parser.add_argument("--end", type=str, help="YYYY-MM-DD, defaults to yesterday")
    parser.add_argument("--forecast-days", type=int, default=7)
    args = parser.parse_args()

    today = date.today()
    start = (
        pd.Timestamp(args.start).date() if args.start else today - timedelta(days=400)
    )
    end = pd.Timestamp(args.end).date() if args.end else today - timedelta(days=1)

    RAW_WEATHER_DIR.mkdir(parents=True, exist_ok=True)

    hist = fetch_historical(start, end)
    hist.to_parquet(HISTORICAL_PATH, index=False)
    print(f"Historical weather: {len(hist)} hourly rows -> {HISTORICAL_PATH}")

    fc = fetch_forecast(days_ahead=args.forecast_days)
    fc.to_parquet(FORECAST_PATH, index=False)
    print(f"Forecast weather: {len(fc)} hourly rows -> {FORECAST_PATH}")


if __name__ == "__main__":
    main()
