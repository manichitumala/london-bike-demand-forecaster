"""Fetch current Santander Cycles docking station metadata (id, name, lat/lon, capacity).

TfL's historical journey extracts only give a station *name* and a "station
number" (the dock terminal id), not coordinates. The live BikePoint API is
the only free source of lat/lon and dock capacity, so we snapshot it
separately and join on station name in SQL. This means stations that have
closed since the journeys were recorded won't get a map position — see
README limitations.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bikeforecast.config import RAW_WEATHER_DIR, TFL_BIKEPOINT_URL

STATIONS_PATH = RAW_WEATHER_DIR.parent / "stations" / "bikepoints.json"


def _prop(props: list[dict], key: str, default=None):
    for p in props:
        if p.get("key") == key:
            return p.get("value")
    return default


def fetch_stations() -> list[dict]:
    resp = requests.get(TFL_BIKEPOINT_URL, timeout=30)
    resp.raise_for_status()
    raw = resp.json()

    stations = []
    for s in raw:
        props = s.get("additionalProperties", [])
        stations.append(
            {
                "bikepoint_id": s["id"],
                "terminal_name": _prop(props, "TerminalName"),
                "common_name": s["commonName"],
                "lat": s["lat"],
                "lon": s["lon"],
                "nb_docks": int(_prop(props, "NbDocks", 0) or 0),
                "nb_bikes": int(_prop(props, "NbBikes", 0) or 0),
                "nb_empty_docks": int(_prop(props, "NbEmptyDocks", 0) or 0),
                "installed": _prop(props, "Installed") == "true",
            }
        )
    return stations


def main() -> None:
    stations = fetch_stations()
    STATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATIONS_PATH.write_text(json.dumps(stations, indent=2), encoding="utf-8")
    print(f"Wrote {len(stations)} stations to {STATIONS_PATH}")


if __name__ == "__main__":
    main()
