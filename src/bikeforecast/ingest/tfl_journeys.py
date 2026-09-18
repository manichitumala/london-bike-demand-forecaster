"""Download TfL Santander Cycles weekly/fortnightly journey extracts.

The bucket at cycling.data.tfl.gov.uk/usage-stats/ has no API for date-range
queries, so we list the whole bucket, parse the date range each file covers
out of its filename (the one part of the naming scheme that's consistent),
and download whatever overlaps the range we asked for.

Filenames are otherwise messy: numbering resets, some have spaces, some
have duplicate keys pointing at the same bytes (same ETag). We dedupe on
(start_date, end_date, size) and prefer the no-space filename when both exist.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

import requests
from dateutil import parser as dateparser
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bikeforecast.config import RAW_JOURNEYS_DIR, TFL_BUCKET_LIST_URL, TFL_CSV_BASE_URL

S3_NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}

# e.g. "16Oct2025-31Oct2025" or "10Jan16-23Jan16"
DATE_RANGE_RE = re.compile(
    r"(\d{1,2}[A-Za-z]{3}\d{2,4})\s*-\s*(\d{1,2}[A-Za-z]{3}\d{2,4})"
)


@dataclass(frozen=True)
class JourneyFile:
    key: str
    size: int
    start: date
    end: date

    @property
    def url(self) -> str:
        return TFL_CSV_BASE_URL + "/".join(
            part.replace(" ", "%20") for part in self.key.split("/")
        )

    @property
    def filename(self) -> str:
        # Normalise away spaces so the local cache doesn't end up with
        # near-duplicate files for the same underlying data.
        return self.key.split("/")[-1].replace(" ", "")


def _parse_date_token(token: str) -> date:
    # dateutil defaults 2-digit years to 20xx, which is what we want here.
    return dateparser.parse(token, dayfirst=True).date()


def list_available_files() -> list[JourneyFile]:
    resp = requests.get(TFL_BUCKET_LIST_URL, timeout=30)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)

    files: dict[tuple[date, date, int], JourneyFile] = {}
    for contents in root.findall("s3:Contents", S3_NS):
        key = contents.findtext("s3:Key", default="", namespaces=S3_NS)
        size = int(contents.findtext("s3:Size", default="0", namespaces=S3_NS))
        if not key.lower().endswith(".csv"):
            continue
        m = DATE_RANGE_RE.search(key)
        if not m:
            continue
        try:
            start = _parse_date_token(m.group(1))
            end = _parse_date_token(m.group(2))
        except (ValueError, OverflowError):
            continue

        dedupe_key = (start, end, size)
        existing = files.get(dedupe_key)
        if existing is None or (" " in existing.key and " " not in key):
            files[dedupe_key] = JourneyFile(key=key, size=size, start=start, end=end)

    return sorted(files.values(), key=lambda f: f.start)


def download_range(
    start: date,
    end: date,
    out_dir: Path = RAW_JOURNEYS_DIR,
    force: bool = False,
) -> list[Path]:
    """Download every journey extract that overlaps [start, end]."""
    out_dir.mkdir(parents=True, exist_ok=True)
    all_files = list_available_files()
    wanted = [f for f in all_files if f.end >= start and f.start <= end]

    if not wanted:
        print(f"No TfL journey files found overlapping {start}..{end}", file=sys.stderr)
        return []

    downloaded: list[Path] = []
    for jf in tqdm(wanted, desc="TfL journey extracts"):
        dest = out_dir / jf.filename
        downloaded.append(dest)
        if dest.exists() and not force:
            continue
        with requests.get(jf.url, stream=True, timeout=120) as r:
            r.raise_for_status()
            tmp = dest.with_suffix(".part")
            with open(tmp, "wb") as fh:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    fh.write(chunk)
            tmp.rename(dest)
    return downloaded


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=str, help="YYYY-MM-DD")
    parser.add_argument("--end", type=str, help="YYYY-MM-DD")
    parser.add_argument(
        "--weeks", type=int, default=None,
        help="Shortcut: download the most recent N weeks instead of --start/--end",
    )
    parser.add_argument("--force", action="store_true", help="Re-download existing files")
    args = parser.parse_args()

    if args.weeks:
        all_files = list_available_files()
        if not all_files:
            print("Could not list TfL bucket", file=sys.stderr)
            sys.exit(1)
        end = all_files[-1].end
        start = end - timedelta(weeks=args.weeks)
    else:
        if not (args.start and args.end):
            print("Pass either --weeks N or both --start and --end", file=sys.stderr)
            sys.exit(1)
        start = datetime.strptime(args.start, "%Y-%m-%d").date()
        end = datetime.strptime(args.end, "%Y-%m-%d").date()

    paths = download_range(start, end, force=args.force)
    print(f"{len(paths)} files ready in {RAW_JOURNEYS_DIR} covering {start}..{end}")


if __name__ == "__main__":
    main()
