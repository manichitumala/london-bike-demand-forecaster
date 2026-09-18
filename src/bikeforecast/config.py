"""Central paths and constants for the pipeline."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = ROOT / "data"
RAW_JOURNEYS_DIR = DATA_DIR / "raw" / "journeys"
RAW_WEATHER_DIR = DATA_DIR / "raw" / "weather"
PROCESSED_DIR = DATA_DIR / "processed"
DB_DIR = DATA_DIR / "db"
DB_PATH = DB_DIR / "bikeforecast.duckdb"

SQL_DIR = Path(__file__).resolve().parent / "transform" / "sql"

# London reference point used for weather (city-wide weather is a fair
# approximation — station-level microclimates are a known limitation, see README).
LONDON_LAT = 51.5074
LONDON_LON = -0.1278
TIMEZONE = "Europe/London"

TFL_BUCKET_LIST_URL = (
    "https://s3-eu-west-1.amazonaws.com/cycling.data.tfl.gov.uk/"
    "?list-type=2&delimiter=/&prefix=usage-stats/"
)
TFL_CSV_BASE_URL = "https://cycling.data.tfl.gov.uk/"
TFL_BIKEPOINT_URL = "https://api.tfl.gov.uk/BikePoint"

OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_HOURLY_VARS = (
    "temperature_2m,precipitation,rain,wind_speed_10m,relative_humidity_2m"
)

GOV_UK_BANK_HOLIDAYS_URL = "https://www.gov.uk/bank-holidays.json"

FORECAST_HORIZON_HOURS = 7 * 24

for _d in (RAW_JOURNEYS_DIR, RAW_WEATHER_DIR, PROCESSED_DIR, DB_DIR):
    _d.mkdir(parents=True, exist_ok=True)
