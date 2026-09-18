"""Fetch UK (England & Wales) bank holidays from the gov.uk open API."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bikeforecast.config import GOV_UK_BANK_HOLIDAYS_URL, RAW_WEATHER_DIR

HOLIDAYS_PATH = RAW_WEATHER_DIR.parent / "calendar" / "bank_holidays.parquet"


def fetch_bank_holidays() -> pd.DataFrame:
    resp = requests.get(GOV_UK_BANK_HOLIDAYS_URL, timeout=30)
    resp.raise_for_status()
    events = resp.json()["england-and-wales"]["events"]
    df = pd.DataFrame(events)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df[["date", "title"]]


def main() -> None:
    df = fetch_bank_holidays()
    HOLIDAYS_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(HOLIDAYS_PATH, index=False)
    print(f"Wrote {len(df)} bank holidays to {HOLIDAYS_PATH}")


if __name__ == "__main__":
    main()
