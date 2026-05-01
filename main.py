import json
from csv import DictReader
from datetime import date, timedelta
from pathlib import Path

import requests


def format_address(record: dict) -> str:
    result = ""

    if len(record["saon"]) > 0:
        result += f"{record['saon'].title()}, "

    result += f"{record['paon'].title()}"
    if record.get("paon", "")[0].isdigit():
        # House number
        result += " "
    else:
        # House name
        result += ", "
    result += f"{record['street'].title()}, "
    result += f"{record['postcode']}"

    return result


PROPERTY_TYPE_LABELS = {
    "D": "Detached",
    "S": "Semi-detached",
    "T": "Terraced",
    "F": "Flat/Maisonette",
    "O": "Other",
}


def geocode_postcodes(postcodes: list[str]) -> dict[str, tuple[float, float]]:
    """Batch geocode UK postcodes using postcodes.io (max 100 per request)."""
    results = {}
    unique_postcodes = list(set(postcodes))
    for i in range(0, len(unique_postcodes), 100):
        batch = unique_postcodes[i : i + 100]
        try:
            resp = requests.post(
                "https://api.postcodes.io/postcodes",
                json={"postcodes": batch},
                timeout=10,
            )
            if resp.status_code == 200:
                for item in resp.json()["result"]:
                    if item["result"] is not None:
                        results[item["query"]] = (
                            item["result"]["latitude"],
                            item["result"]["longitude"],
                        )
        except requests.RequestException:
            print(f"Warning: failed to geocode batch of {len(batch)} postcodes")
    return results


def generate_report_html(
    report_date: str,
    sections: list[dict],
) -> str:
    """Generate an HTML report page with a table and map."""
    sales_json = json.dumps(
        [
            {
                "address": s["address"],
                "lat": s["lat"],
                "lng": s["lng"],
                "price": s["price"],
                "date": s["date"],
                "type": s["type"],
                "postcode_area": s["postcode_area"],
            }
            for s in sections
            if s["lat"] is not None
        ]
    )

    list_html = ""
    for i, s in enumerate(sections):
        list_html += f'        <li data-index="{i}">{s["address"]}</li>\n'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>House Sales Report &mdash; {report_date}</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    html, body {{ height: 100%; overflow: hidden; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #333; background: #f5f5f5; display: flex; flex-direction: column; }}
    header {{ background: #2c3e50; color: white; padding: 1.5rem 2rem; flex-shrink: 0; }}
    header h1 {{ font-size: 1.5rem; font-weight: 600; }}
    header a {{ color: #ecf0f1; text-decoration: none; font-size: 0.9rem; }}
    header a:hover {{ text-decoration: underline; }}
    .content {{ display: flex; flex: 1; min-height: 0; }}
    .sidebar {{ width: 440px; flex-shrink: 0; overflow-y: auto; background: white; border-right: 1px solid #ddd; }}
    .sidebar .summary {{ padding: 0.6rem 1rem; color: #666; font-size: 0.8rem; background: #f0f0f0; border-bottom: 1px solid #ddd; }}
    .sidebar ul {{ list-style: none; }}
    .sidebar li {{ padding: 0.5rem 1rem; border-bottom: 1px solid #eee; font-size: 0.85rem; cursor: pointer; }}
    .sidebar li:hover {{ background: #f9f9f9; }}
    #map {{ flex: 1; }}
  </style>
</head>
<body>
  <header>
    <a href="index.html">&larr; All reports</a>
    <h1>House Sales Report &mdash; {report_date}</h1>
  </header>
  <div class="content">
    <div class="sidebar">
      <p class="summary">{len(sections)} new sale(s) detected.</p>
      <ul>
{list_html}      </ul>
    </div>
    <div id="map"></div>
  </div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    var sales = {sales_json};
    var map = L.map('map').setView([53.48, -3.04], 13);
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19
    }}).addTo(map);
    var defaultIcon = L.icon({{
      iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
      shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
      iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41]
    }});
    var redIcon = L.icon({{
      iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png',
      shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
      iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41]
    }});
    var bounds = [];
    var markers = {{}};
    sales.forEach(function(s, i) {{
      var marker = L.marker([s.lat, s.lng], {{icon: defaultIcon}}).addTo(map);
      var price = s.price ? '&pound;' + Number(s.price).toLocaleString() : 'N/A';
      marker.bindPopup('<strong>' + s.address + '</strong><br>Date: ' + s.date + '<br>Price: ' + price + '<br>Type: ' + s.type);
      bounds.push([s.lat, s.lng]);
      markers[i] = marker;
    }});
    if (bounds.length > 0) {{
      map.fitBounds(bounds, {{ padding: [40, 40] }});
    }}
    document.querySelectorAll('.sidebar li[data-index]').forEach(function(li) {{
      var idx = Number(li.getAttribute('data-index'));
      li.addEventListener('mouseenter', function() {{
        if (markers[idx]) markers[idx].setIcon(redIcon);
      }});
      li.addEventListener('mouseleave', function() {{
        if (markers[idx]) markers[idx].setIcon(defaultIcon);
      }});
    }})
  </script>
</body>
</html>
"""


def generate_index_html(docs_dir: Path) -> None:
    """Generate index.html listing all report pages, newest first."""
    report_files = sorted(docs_dir.glob("*.html"), reverse=True)
    report_files = [f for f in report_files if f.name != "index.html"]

    links_html = ""
    for f in report_files:
        report_date = f.stem
        links_html += f'    <li><a href="{f.name}">{report_date}</a></li>\n'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>House Sales Reports</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #333; background: #f5f5f5; }}
    header {{ background: #2c3e50; color: white; padding: 1.5rem 2rem; }}
    header h1 {{ font-size: 1.5rem; font-weight: 600; }}
    .container {{ max-width: 800px; margin: 1.5rem auto; padding: 0 1rem; }}
    ul {{ list-style: none; }}
    li {{ margin: 0.5rem 0; }}
    a {{ color: #2980b9; text-decoration: none; font-size: 1.1rem; }}
    a:hover {{ text-decoration: underline; }}
    .empty {{ color: #999; font-style: italic; }}
  </style>
</head>
<body>
  <header>
    <h1>House Sales Reports</h1>
  </header>
  <div class="container">
    <ul>
{links_html}    </ul>
    {"<p class='empty'>No reports yet.</p>" if not report_files else ""}
  </div>
</body>
</html>
"""
    (docs_dir / "index.html").write_text(html)


CSV_DOWNLOAD_URL_FORMAT = "https://landregistry.data.gov.uk/app/ppd/ppd_data.csv?header=true&limit=all&min_date={min_date}&postcode={postcode_area}"

DATA_DIR_ROOT = Path(__file__).parent / "data"
REPORT_DIR = Path(__file__).parent / "reports"
DOCS_DIR = Path(__file__).parent / "docs"


def main():
    today = date.today()
    min_date = today - timedelta(days=180)

    all_new_sales = []

    for postcode_area in ["L22", "L23"]:
        data_dir = DATA_DIR_ROOT / postcode_area
        data_dir.mkdir(parents=True, exist_ok=True)
        try:
            # Get latest previous data file, build a set of unique IDs
            previous_data_path = sorted(data_dir.iterdir())[-1]
            previous_data = DictReader(previous_data_path.open())
            previous_unique_ids = {record["unique_id"] for record in previous_data}
        except IndexError:
            previous_unique_ids = set()
        # Download the latest data
        current_data_path = data_dir / f"{today.isoformat()}.csv"
        url = CSV_DOWNLOAD_URL_FORMAT.format(
            min_date=min_date, postcode_area=postcode_area
        )
        resp = requests.get(url)
        with current_data_path.open("w") as f:
            f.write(resp.text)

        # Read in the latest data, collect new sales
        current_data = DictReader(current_data_path.open())
        for record in current_data:
            if record["unique_id"] not in previous_unique_ids:
                address = format_address(record)
                print(f"{record['unique_id']}: {address}")
                all_new_sales.append(
                    {
                        "address": address,
                        "postcode": record["postcode"],
                        "price": record["price_paid"],
                        "date": record["deed_date"],
                        "type": PROPERTY_TYPE_LABELS.get(
                            record["property_type"], record["property_type"]
                        ),
                        "postcode_area": postcode_area,
                    }
                )

    # Geocode all postcodes
    postcodes = [s["postcode"] for s in all_new_sales]
    coords = geocode_postcodes(postcodes)

    for sale in all_new_sales:
        lat_lng = coords.get(sale["postcode"])
        sale["lat"] = lat_lng[0] if lat_lng else None
        sale["lng"] = lat_lng[1] if lat_lng else None

    # Generate markdown report
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    md_path = REPORT_DIR / f"{today.isoformat()}.md"
    with md_path.open("w") as f:
        for postcode_area in ["L22", "L23"]:
            area_sales = [s for s in all_new_sales if s["postcode_area"] == postcode_area]
            f.write(f"# Sales in {postcode_area}\n\n")
            for s in area_sales:
                f.write(f"* {s['address']}\n")
            f.write("\n")
    print(f"Markdown report written to {md_path}")

    # Generate HTML report
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = DOCS_DIR / f"{today.isoformat()}.html"
    report_path.write_text(generate_report_html(today.isoformat(), all_new_sales))
    print(f"Report written to {report_path}")

    # Regenerate index page
    generate_index_html(DOCS_DIR)
    print(f"Index written to {DOCS_DIR / 'index.html'}")


if __name__ == "__main__":
    main()
