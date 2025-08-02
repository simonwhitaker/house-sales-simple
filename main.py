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


CSV_DOWNLOAD_URL_FORMAT = "https://landregistry.data.gov.uk/app/ppd/ppd_data.csv?header=true&limit=all&min_date={min_date}&postcode={postcode_area}"
DATA_DIR_ROOT = Path("data")
REPORT_DIR = Path("reports")

today = date.today()
min_date = today - timedelta(days=180)


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
    url = CSV_DOWNLOAD_URL_FORMAT.format(min_date=min_date, postcode_area=postcode_area)
    resp = requests.get(url)
    with current_data_path.open("w") as f:
        f.write(resp.text)

    # Read in the latest data, report on any sales we haven't previously seen
    current_data = DictReader(current_data_path.open())
    report_path = REPORT_DIR / f"{today.isoformat()}.md"
    with report_path.open("a") as f:
        f.write(f"# Sales in {postcode_area}\n\n")
        for record in current_data:
            if record["unique_id"] not in previous_unique_ids:
                line = format_address(record)
                f.write(f"* {line}\n")
                print(f"{record['unique_id']}: {line}")
        f.write("\n")
