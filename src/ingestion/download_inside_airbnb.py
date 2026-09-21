"""Download a dated Copenhagen Inside Airbnb snapshot.

Raw files are stored outside version control. The script records URLs,
checksums, sizes, and retrieval times in data/metadata/source_manifest.json.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from common import PROJECT_ROOT, download_url, update_manifest, utc_now, write_json


ASSETS = {
    "listings_detailed": "data/listings.csv.gz",
    "calendar_detailed": "data/calendar.csv.gz",
    "reviews_detailed": "data/reviews.csv.gz",
    "listings_summary": "visualisations/listings.csv",
    "reviews_summary": "visualisations/reviews.csv",
    "neighbourhoods": "visualisations/neighbourhoods.csv",
    "neighbourhoods_geojson": "visualisations/neighbourhoods.geojson",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default="2026-06-30", help="Inside Airbnb snapshot date (YYYY-MM-DD).")
    parser.add_argument("--force", action="store_true", help="Re-download files that already exist.")
    parser.add_argument(
        "--assets",
        nargs="+",
        choices=sorted(ASSETS),
        default=sorted(ASSETS),
        help="Named assets to download; defaults to all listed assets.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    base_url = f"https://data.insideairbnb.com/denmark/hovedstaden/copenhagen/{args.date}"
    destination_root = PROJECT_ROOT / "data" / "raw" / "inside_airbnb" / "copenhagen" / args.date
    entries = []

    for name in args.assets:
        relative_asset = ASSETS[name]
        url = f"{base_url}/{relative_asset}"
        destination = destination_root / relative_asset
        print(f"[{name}] {url}")
        entry = download_url(url, destination, force=args.force)
        entry.update({"provider": "Inside Airbnb", "asset": name, "snapshot_date": args.date})
        entries.append(entry)
        print(f"  -> {entry['status']}: {entry['size_bytes']:,} bytes; sha256={entry['sha256'][:16]}…")

    update_manifest(entries)
    metadata = {
        "provider": "Inside Airbnb",
        "city": "Copenhagen",
        "snapshot_date": args.date,
        "landing_page": "https://insideairbnb.com/get-the-data/",
        "assumptions_page": "https://insideairbnb.com/data-assumptions/",
        "license": "Creative Commons Attribution 4.0 International",
        "retrieved_at_utc": utc_now(),
        "assets": args.assets,
        "raw_directory": destination_root.relative_to(PROJECT_ROOT).as_posix(),
        "notes": [
            "Coordinates are provider-anonymised and should not support fine-grained address claims.",
            "Raw files are excluded from version control; preserve the checksums in the source manifest.",
        ],
    }
    write_json(destination_root / "snapshot_metadata.json", metadata)
    print(f"\nSaved Inside Airbnb metadata to {destination_root.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
