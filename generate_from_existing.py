"""One-off script to regenerate HTML reports from existing CSV data files.

Usage: uv run python generate_from_existing.py

This reads all CSV files in data/, detects new sales for each period,
geocodes the postcodes, and writes HTML reports to docs/.
"""

from csv import DictReader
from pathlib import Path

from main import (
    PROPERTY_TYPE_LABELS,
    format_address,
    generate_index_html,
    generate_report_html,
    geocode_postcodes,
    DATA_DIR_ROOT,
    DOCS_DIR,
)

DOCS_DIR.mkdir(parents=True, exist_ok=True)

# Get all data dates (sorted)
dates = sorted(
    {f.stem for area in ["L22", "L23"] for f in (DATA_DIR_ROOT / area).glob("*.csv")}
)

for i, current_date in enumerate(dates):
    if i == 0:
        continue  # skip first date, no previous to compare against

    prev_date = dates[i - 1]
    all_new_sales = []

    for postcode_area in ["L22", "L23"]:
        prev_path = DATA_DIR_ROOT / postcode_area / f"{prev_date}.csv"
        curr_path = DATA_DIR_ROOT / postcode_area / f"{current_date}.csv"

        if not curr_path.exists():
            continue

        prev_ids = set()
        if prev_path.exists():
            prev_ids = {r["unique_id"] for r in DictReader(prev_path.open())}

        for record in DictReader(curr_path.open()):
            if record["unique_id"] not in prev_ids:
                all_new_sales.append(
                    {
                        "address": format_address(record),
                        "postcode": record["postcode"],
                        "price": record["price_paid"],
                        "date": record["deed_date"],
                        "type": PROPERTY_TYPE_LABELS.get(
                            record["property_type"], record["property_type"]
                        ),
                        "postcode_area": postcode_area,
                    }
                )

    if not all_new_sales:
        continue

    # Geocode
    postcodes = [s["postcode"] for s in all_new_sales]
    coords = geocode_postcodes(postcodes)
    for sale in all_new_sales:
        lat_lng = coords.get(sale["postcode"])
        sale["lat"] = lat_lng[0] if lat_lng else None
        sale["lng"] = lat_lng[1] if lat_lng else None

    report_path = DOCS_DIR / f"{current_date}.html"
    report_path.write_text(generate_report_html(current_date, all_new_sales))
    print(f"Generated {report_path} ({len(all_new_sales)} sales)")

generate_index_html(DOCS_DIR)
print("Generated index.html")
