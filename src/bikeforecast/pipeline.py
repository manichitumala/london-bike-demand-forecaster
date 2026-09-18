"""End-to-end pipeline entry point: ingest -> load -> build features -> train -> forecast.

    python -m bikeforecast.pipeline               # incremental: last 8 weeks of journeys
    python -m bikeforecast.pipeline --weeks 104    # ~2 years, for a full backfill
    python -m bikeforecast.pipeline --skip-train   # refresh data + forecast, reuse existing models

This is what both the GitHub Action and a local refresh call.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bikeforecast.ingest import bank_holidays, tfl_journeys, tfl_stations
from bikeforecast.transform import load_duckdb


def step(name: str, fn, *args, **kwargs) -> None:
    print(f"\n===== {name} =====", flush=True)
    t0 = time.time()
    fn(*args, **kwargs)
    print(f"----- {name} done in {time.time() - t0:.1f}s -----", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weeks", type=int, default=8, help="Weeks of TfL journeys to (re)fetch")
    parser.add_argument("--skip-ingest", action="store_true")
    parser.add_argument("--skip-train", action="store_true", help="Reuse existing trained models")
    args = parser.parse_args()

    if not args.skip_ingest:
        from datetime import timedelta

        all_files = tfl_journeys.list_available_files()
        end = all_files[-1].end
        start = end - timedelta(weeks=args.weeks)
        step(
            f"Ingest: TfL journeys ({start}..{end})",
            tfl_journeys.download_range, start, end,
        )
        step("Ingest: BikePoint station metadata", tfl_stations.main)
        step("Ingest: UK bank holidays", bank_holidays.main)
        step(f"Ingest: weather ({start}..{end})", _fetch_weather_for_range, start, end)

    step("Transform: load raw data + run SQL build", load_duckdb.build)

    if not args.skip_train:
        from bikeforecast.models import train

        step("Model: train + evaluate", train.main)

    from bikeforecast.models import forecast

    step("Forecast: generate 7-day forecast + station risk", forecast.main)

    print("\nPipeline complete. Launch the dashboard with:\n"
          "  streamlit run dashboard/app.py")


def _fetch_weather_for_range(start, end) -> None:
    from datetime import timedelta

    from bikeforecast.ingest.weather import (
        FORECAST_PATH,
        HISTORICAL_PATH,
        fetch_forecast,
        fetch_historical,
    )

    hist = fetch_historical(start - timedelta(days=8), end + timedelta(days=8))
    hist.to_parquet(HISTORICAL_PATH, index=False)
    fc = fetch_forecast()
    fc.to_parquet(FORECAST_PATH, index=False)


if __name__ == "__main__":
    main()
