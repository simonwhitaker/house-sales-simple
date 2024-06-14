from csv import DictReader
from datetime import date, timedelta
from pathlib import Path
from urllib.request import urlopen


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
DATA_DIR = Path("data")
REPORT_DIR = Path("reports")

today = date.today()
min_date = today - timedelta(days=180)

try:
    # Get latest previous data file, build a set of unique IDs
    previous_data_path = sorted(DATA_DIR.iterdir())[-1]
    previous_data = DictReader(previous_data_path.open())
    previous_unique_ids = {record["unique_id"] for record in previous_data}
except IndexError:
    previous_unique_ids = {}

# Download the latest data
current_data_path = DATA_DIR / f"{today.isoformat()}.csv"
url = CSV_DOWNLOAD_URL_FORMAT.format(min_date=min_date, postcode_area="L23")
resp = urlopen(url)
with current_data_path.open("w") as f:
    f.write(resp.read().decode("utf-8"))

# Read in the latest data, report on any sales we haven't previously seen
current_data = DictReader(current_data_path.open())
report_path = REPORT_DIR / f"{today.isoformat()}.md"
with report_path.open("w") as f:
    for record in current_data:
        if record["unique_id"] not in previous_unique_ids:
            line = (
                f"{format_address(record)} ({date.fromisoformat(record['deed_date'])})"
            )
            f.write(f"* {line}\n")
            print(f"{record['unique_id']}: {line})")
