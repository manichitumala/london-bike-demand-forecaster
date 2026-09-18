"""Load raw ingested files (CSV/JSON/Parquet) into DuckDB `raw_*` tables,
then run the SQL build scripts on top of them.
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bikeforecast.config import (
    DB_PATH,
    RAW_JOURNEYS_DIR,
    RAW_WEATHER_DIR,
    SQL_DIR,
)

STATIONS_JSON = RAW_WEATHER_DIR.parent / "stations" / "bikepoints.json"
HOLIDAYS_PARQUET = RAW_WEATHER_DIR.parent / "calendar" / "bank_holidays.parquet"


def load_raw(con: duckdb.DuckDBPyConnection) -> None:
    journeys_glob = str(RAW_JOURNEYS_DIR / "*.csv").replace("\\", "/")
    con.execute(
        f"""
        CREATE OR REPLACE TABLE raw_journeys AS
        SELECT * FROM read_csv(
            '{journeys_glob}',
            union_by_name = true,
            filename = false
        )
        """
    )

    stations_path = str(STATIONS_JSON).replace("\\", "/")
    con.execute(
        f"""
        CREATE OR REPLACE TABLE raw_stations AS
        SELECT * FROM read_json_auto('{stations_path}')
        """
    )

    hist_path = str(RAW_WEATHER_DIR / "historical.parquet").replace("\\", "/")
    fc_path = str(RAW_WEATHER_DIR / "forecast.parquet").replace("\\", "/")
    con.execute(
        f"""
        CREATE OR REPLACE TABLE raw_weather_historical AS
        SELECT * FROM read_parquet('{hist_path}')
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TABLE raw_weather_forecast AS
        SELECT * FROM read_parquet('{fc_path}')
        """
    )

    holidays_path = str(HOLIDAYS_PARQUET).replace("\\", "/")
    con.execute(
        f"""
        CREATE OR REPLACE TABLE raw_bank_holidays AS
        SELECT * FROM read_parquet('{holidays_path}')
        """
    )


def run_sql_dir(con: duckdb.DuckDBPyConnection, sql_dir: Path = SQL_DIR) -> None:
    for sql_file in sorted(sql_dir.glob("*.sql")):
        print(f"-- running {sql_file.name}")
        con.execute(sql_file.read_text(encoding="utf-8"))


def build(db_path: Path = DB_PATH) -> None:
    con = duckdb.connect(str(db_path))
    try:
        load_raw(con)
        run_sql_dir(con)
    finally:
        con.close()


if __name__ == "__main__":
    build()
    print(f"Build complete -> {DB_PATH}")
