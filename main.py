import json
from csv import DictReader
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
from time import sleep

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


REQUIRED_CSV_FIELDS = {
    "unique_id",
    "price_paid",
    "deed_date",
    "postcode",
    "property_type",
    "saon",
    "paon",
    "street",
}
DOWNLOAD_ATTEMPTS = 3
DOWNLOAD_TIMEOUT_SECONDS = 30
RETRY_DELAY_SECONDS = 2


def preview_response(text: str) -> str:
    preview = text[:500].replace("\r", "\\r").replace("\n", "\\n")
    return preview if preview else "<empty response>"


def validate_sales_csv(csv_text: str, url: str) -> None:
    reader = DictReader(StringIO(csv_text))
    fieldnames = set(reader.fieldnames or [])
    missing_fields = REQUIRED_CSV_FIELDS - fieldnames
    if not missing_fields:
        return

    missing = ", ".join(sorted(missing_fields))
    raise ValueError(
        f"Downloaded CSV from {url} is missing required column(s): {missing}. "
        f"Header: {reader.fieldnames!r}. Response preview: {preview_response(csv_text)!r}"
    )


def download_sales_csv(url: str) -> str:
    last_error = None
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            resp = requests.get(url, timeout=DOWNLOAD_TIMEOUT_SECONDS)
            resp.raise_for_status()
            validate_sales_csv(resp.text, url)
            return resp.text
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt == DOWNLOAD_ATTEMPTS:
                break
            print(f"Warning: attempt {attempt} to download sales CSV failed: {exc}")
            sleep(RETRY_DELAY_SECONDS)

    raise RuntimeError(
        f"Failed to download valid sales CSV after {DOWNLOAD_ATTEMPTS} attempts: "
        f"{last_error}"
    ) from last_error


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


def format_display_date(date_str: str) -> str:
    """Format an ISO date string like '2026-06-01' as '1 June 2026'."""
    try:
        parsed = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return date_str
    return f"{parsed.day} {parsed.strftime('%B %Y')}"


def format_display_price(price: str) -> str:
    try:
        return f"£{int(price):,}"
    except (TypeError, ValueError):
        return "Price N/A"


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
                "date": format_display_date(s["date"]),
                "type": s["type"],
                "postcode_area": s["postcode_area"],
            }
            for s in sections
        ]
    )

    list_html = ""
    for i, s in enumerate(sections):
        price = format_display_price(s["price"])
        sale_date = format_display_date(s["date"])
        list_html += f"""        <li data-index="{i}" tabindex="0">
          <span class="address">{s["address"]}</span>
          <span class="meta"><span class="price">{price}</span><span class="dot"></span>{s["type"]}<span class="dot"></span>{sale_date}</span>
        </li>
"""

    count = len(sections)
    count_label = f"{count} new sale{'s' if count != 1 else ''}"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>House Sales &mdash; {format_display_date(report_date)}</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <style>
    :root {{
      --bg: #f8fafc;
      --surface: #ffffff;
      --border: #e2e8f0;
      --text: #0f172a;
      --text-muted: #64748b;
      --accent: #4f46e5;
      --accent-soft: #eef2ff;
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    html, body {{ height: 100%; overflow: hidden; }}
    body {{
      font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
      color: var(--text);
      background: var(--bg);
      display: flex;
      flex-direction: column;
      -webkit-font-smoothing: antialiased;
    }}
    header {{
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 1rem 1.5rem;
      flex-shrink: 0;
      display: flex;
      align-items: center;
      gap: 1rem;
    }}
    .header-text {{ min-width: 0; }}
    .eyebrow {{
      display: block;
      font-size: 0.7rem;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--text-muted);
    }}
    header h1 {{ font-size: 1.15rem; font-weight: 700; letter-spacing: -0.01em; }}
    .back-link {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 2.25rem;
      height: 2.25rem;
      border-radius: 0.6rem;
      border: 1px solid var(--border);
      color: var(--text-muted);
      text-decoration: none;
      font-size: 1.1rem;
      flex-shrink: 0;
      transition: all 0.15s ease;
    }}
    .back-link:hover {{ color: var(--accent); border-color: var(--accent); background: var(--accent-soft); }}
    .count-pill {{
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 0.75rem;
      font-weight: 600;
      padding: 0.25rem 0.7rem;
      border-radius: 999px;
      white-space: nowrap;
    }}
    .repo-link {{
      margin-left: auto;
      color: var(--text-muted);
      text-decoration: none;
      font-size: 0.8rem;
      font-weight: 500;
      white-space: nowrap;
    }}
    .repo-link:hover {{ color: var(--accent); }}
    .content {{ display: flex; flex: 1; min-height: 0; }}
    .sidebar {{
      width: 420px;
      flex-shrink: 0;
      overflow-y: auto;
      background: var(--surface);
      border-right: 1px solid var(--border);
      padding: 0.75rem;
    }}
    .sidebar ul {{ list-style: none; display: flex; flex-direction: column; gap: 0.5rem; }}
    .sidebar li {{
      padding: 0.7rem 0.85rem;
      border: 1px solid var(--border);
      border-radius: 0.75rem;
      cursor: pointer;
      transition: all 0.15s ease;
    }}
    .sidebar li:hover, .sidebar li:focus-visible, .sidebar li.active {{
      border-color: var(--accent);
      background: var(--accent-soft);
      outline: none;
    }}
    .sidebar .address {{ display: block; font-size: 0.85rem; font-weight: 600; line-height: 1.35; }}
    .sidebar .meta {{
      display: flex;
      align-items: center;
      gap: 0.45rem;
      margin-top: 0.3rem;
      font-size: 0.75rem;
      color: var(--text-muted);
    }}
    .sidebar .price {{ color: var(--accent); font-weight: 700; }}
    .sidebar .dot {{ width: 3px; height: 3px; border-radius: 50%; background: currentColor; opacity: 0.5; }}
    #map {{ flex: 1; }}
    .leaflet-popup-content-wrapper {{
      border-radius: 0.75rem;
      box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.15);
      font-family: inherit;
    }}
    .leaflet-popup-content {{ margin: 0.8rem 1rem; font-size: 0.8rem; line-height: 1.5; }}
    .popup-address {{ font-weight: 700; font-size: 0.85rem; display: block; margin-bottom: 0.2rem; }}
    .popup-price {{ color: var(--accent); font-weight: 700; }}
    @media (max-width: 700px) {{
      html, body {{ overflow: auto; }}
      header {{ flex-wrap: wrap; row-gap: 0.5rem; }}
      .content {{ flex-direction: column-reverse; }}
      .sidebar {{ width: 100%; border-right: none; border-top: 1px solid var(--border); }}
      #map {{ min-height: 55vh; }}
    }}
  </style>
</head>
<body>
  <header>
    <a class="back-link" href="index.html" aria-label="All reports">&larr;</a>
    <div class="header-text">
      <span class="eyebrow">House Sales Report</span>
      <h1>{format_display_date(report_date)}</h1>
    </div>
    <span class="count-pill">{count_label}</span>
    <a class="repo-link" href="https://github.com/simonwhitaker/house-sales-simple">View on GitHub</a>
  </header>
  <div class="content">
    <div class="sidebar">
      <ul>
{list_html}      </ul>
    </div>
    <div id="map"></div>
  </div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    var sales = {sales_json};
    var map = L.map('map').setView([53.48, -3.04], 13);
    L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
      maxZoom: 19
    }}).addTo(map);
    var baseStyle = {{ radius: 8, color: '#4f46e5', weight: 2, fillColor: '#4f46e5', fillOpacity: 0.35 }};
    var activeStyle = {{ radius: 11, color: '#312e81', weight: 3, fillColor: '#4f46e5', fillOpacity: 0.75 }};
    var bounds = [];
    var markers = {{}};
    sales.forEach(function(s, i) {{
      if (s.lat === null || s.lng === null) return;
      var marker = L.circleMarker([s.lat, s.lng], baseStyle).addTo(map);
      var price = s.price ? '&pound;' + Number(s.price).toLocaleString() : 'Price N/A';
      marker.bindPopup(
        '<span class="popup-address">' + s.address + '</span>' +
        '<span class="popup-price">' + price + '</span><br>' +
        s.type + '<br>Sold ' + s.date
      );
      bounds.push([s.lat, s.lng]);
      markers[i] = marker;
    }});
    if (bounds.length > 0) {{
      map.fitBounds(bounds, {{ padding: [40, 40] }});
    }}
    document.querySelectorAll('.sidebar li[data-index]').forEach(function(li) {{
      var idx = Number(li.getAttribute('data-index'));
      li.addEventListener('mouseenter', function() {{
        if (markers[idx]) markers[idx].setStyle(activeStyle);
      }});
      li.addEventListener('mouseleave', function() {{
        if (markers[idx]) markers[idx].setStyle(baseStyle);
      }});
      li.addEventListener('click', function() {{
        if (markers[idx]) {{
          map.panTo(markers[idx].getLatLng());
          markers[idx].openPopup();
        }}
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
        links_html += f"""      <li><a href="{f.name}">
        <span class="card-date">{format_display_date(f.stem)}</span>
        <span class="card-cta">View report &rarr;</span>
      </a></li>
"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>House Sales Reports</title>
  <style>
    :root {{
      --bg: #f8fafc;
      --surface: #ffffff;
      --border: #e2e8f0;
      --text: #0f172a;
      --text-muted: #64748b;
      --accent: #4f46e5;
      --accent-soft: #eef2ff;
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
      color: var(--text);
      background: var(--bg);
      -webkit-font-smoothing: antialiased;
    }}
    header {{
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 1rem 1.5rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
    }}
    header h1 {{ font-size: 1.15rem; font-weight: 700; letter-spacing: -0.01em; }}
    .repo-link {{ color: var(--text-muted); text-decoration: none; font-size: 0.8rem; font-weight: 500; }}
    .repo-link:hover {{ color: var(--accent); }}
    .container {{ max-width: 900px; margin: 2rem auto; padding: 0 1.5rem; }}
    .subtitle {{ color: var(--text-muted); font-size: 0.9rem; margin-bottom: 1.5rem; }}
    ul {{
      list-style: none;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 0.75rem;
    }}
    li a {{
      display: block;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 0.75rem;
      padding: 1rem 1.1rem;
      text-decoration: none;
      transition: all 0.15s ease;
    }}
    li a:hover {{
      border-color: var(--accent);
      box-shadow: 0 4px 12px -2px rgba(79, 70, 229, 0.15);
      transform: translateY(-1px);
    }}
    .card-date {{ display: block; font-size: 0.95rem; font-weight: 600; color: var(--text); }}
    .card-cta {{ display: block; margin-top: 0.35rem; font-size: 0.75rem; font-weight: 500; color: var(--accent); }}
    .empty {{ color: var(--text-muted); font-style: italic; }}
  </style>
</head>
<body>
  <header>
    <h1>House Sales Reports</h1>
    <a class="repo-link" href="https://github.com/simonwhitaker/house-sales-simple">View on GitHub</a>
  </header>
  <div class="container">
    <p class="subtitle">New residential sales detected in L22 &amp; L23, newest first.</p>
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
        csv_text = download_sales_csv(url)
        with current_data_path.open("w") as f:
            f.write(csv_text)

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
            area_sales = [
                s for s in all_new_sales if s["postcode_area"] == postcode_area
            ]
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
