import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
import pandas as pd
import re

# ============================================================
# CONFIGURATION
# ============================================================

CITY = "Tirupati"
GEONAME_ID = "1254360"
TIMEZONE = "Asia/Kolkata"

# NSE market window
MARKET_START = "09:15"
MARKET_END = "15:30"

OUTPUT_DIR = Path("data")
OUTPUT_DIR.mkdir(exist_ok=True)

IST = ZoneInfo(TIMEZONE)

# Traditional planetary Hora sequence
CHALDEAN_ORDER = [
    "Saturn",
    "Jupiter",
    "Mars",
    "Sun",
    "Venus",
    "Mercury",
    "Moon"
]

# First Hora lord for each weekday
# Python weekday:
# Monday = 0 ... Sunday = 6
DAY_LORD = {
    0: "Moon",
    1: "Mars",
    2: "Mercury",
    3: "Jupiter",
    4: "Venus",
    5: "Saturn",
    6: "Sun"
}


# ============================================================
# FETCH DRIK PANCHANG
# ============================================================

def fetch_panchang(date_obj):

    date_string = date_obj.strftime("%d/%m/%Y")

    url = (
        "https://www.drikpanchang.com/panchang/"
        "day-panchang.html"
        f"?date={date_string.replace('/', '%2F')}"
        f"&geoname-id={GEONAME_ID}"
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/153 Safari/537.36"
        )
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    text = soup.get_text(
        " ",
        strip=True
    )

    return text


# ============================================================
# EXTRACT SUNRISE / SUNSET
# ============================================================

def extract_sun_times(text):

    sunrise = re.search(
        r"Sunrise\s*([0-9]{1,2}:[0-9]{2})",
        text,
        re.IGNORECASE
    )

    sunset = re.search(
        r"Sunset\s*([0-9]{1,2}:[0-9]{2})",
        text,
        re.IGNORECASE
    )

    if not sunrise:
        raise RuntimeError(
            "Could not find Sunrise in Drik Panchang page."
        )

    if not sunset:
        raise RuntimeError(
            "Could not find Sunset in Drik Panchang page."
        )

    return sunrise.group(1), sunset.group(1)


# ============================================================
# LOCAL DATETIME
# ============================================================

def make_datetime(date_obj, time_string):

    hour, minute = map(
        int,
        time_string.split(":")
    )

    return datetime(
        date_obj.year,
        date_obj.month,
        date_obj.day,
        hour,
        minute,
        tzinfo=IST
    )


# ============================================================
# CALCULATE 24 HORA
# ============================================================

def calculate_24_horas(
    date_obj,
    sunrise,
    sunset,
    next_sunrise
):

    sunrise_dt = make_datetime(
        date_obj,
        sunrise
    )

    sunset_dt = make_datetime(
        date_obj,
        sunset
    )

    next_sunrise_dt = make_datetime(
        date_obj + timedelta(days=1),
        next_sunrise
    )

    # --------------------------------------------------------
    # DAY
    # --------------------------------------------------------

    day_duration = (
        sunset_dt - sunrise_dt
    )

    day_hora_duration = (
        day_duration / 12
    )

    # --------------------------------------------------------
    # NIGHT
    # --------------------------------------------------------

    night_duration = (
        next_sunrise_dt - sunset_dt
    )

    night_hora_duration = (
        night_duration / 12
    )

    # --------------------------------------------------------
    # FIRST HORA LORD
    # --------------------------------------------------------

    weekday = date_obj.weekday()

    first_lord = DAY_LORD[weekday]

    first_index = CHALDEAN_ORDER.index(
        first_lord
    )

    rows = []

    # --------------------------------------------------------
    # DAY HORAS
    # --------------------------------------------------------

    current = sunrise_dt

    for i in range(12):

        planet = CHALDEAN_ORDER[
            (first_index + i) % 7
        ]

        end = (
            current +
            day_hora_duration
        )

        rows.append({
            "Date": date_obj.strftime("%Y-%m-%d"),
            "Period": "Day",
            "Hora": i + 1,
            "Planet": planet,
            "Start": current,
            "End": end
        })

        current = end

    # --------------------------------------------------------
    # NIGHT HORAS
    # --------------------------------------------------------

    current = sunset_dt

    for i in range(12):

        planet = CHALDEAN_ORDER[
            (first_index + 12 + i) % 7
        ]

        end = (
            current +
            night_hora_duration
        )

        rows.append({
            "Date": date_obj.strftime("%Y-%m-%d"),
            "Period": "Night",
            "Hora": i + 13,
            "Planet": planet,
            "Start": current,
            "End": end
        })

        current = end

    return rows


# ============================================================
# CLIP HORA TO MARKET HOURS
# ============================================================

def create_market_horas(
    hora_rows,
    date_obj
):

    market_start = make_datetime(
        date_obj,
        MARKET_START
    )

    market_end = make_datetime(
        date_obj,
        MARKET_END
    )

    market_rows = []

    for row in hora_rows:

        hora_start = row["Start"]
        hora_end = row["End"]

        # Find overlap
        start = max(
            hora_start,
            market_start
        )

        end = min(
            hora_end,
            market_end
        )

        # No overlap
        if start >= end:
            continue

        duration_minutes = (
            end - start
        ).total_seconds() / 60

        market_rows.append({

            "Date":
                date_obj.strftime("%Y-%m-%d"),

            "Market_Start":
                market_start.strftime("%H:%M:%S"),

            "Market_End":
                market_end.strftime("%H:%M:%S"),

            "Hora":
                row["Hora"],

            "Planet":
                row["Planet"],

            "Hora_Start":
                hora_start.strftime("%H:%M:%S"),

            "Hora_End":
                hora_end.strftime("%H:%M:%S"),

            "Market_Overlap_Start":
                start.strftime("%H:%M:%S"),

            "Market_Overlap_End":
                end.strftime("%H:%M:%S"),

            "Overlap_Minutes":
                round(duration_minutes, 2)
        })

    return market_rows


# ============================================================
# GET ONE DAY
# ============================================================

def process_date(date_obj):

    print()
    print("=" * 70)
    print("Processing:", date_obj.strftime("%Y-%m-%d"))
    print("=" * 70)

    # Current date
    text = fetch_panchang(
        date_obj
    )

    sunrise, sunset = extract_sun_times(
        text
    )

    # Tomorrow is needed because night Hora ends
    # at tomorrow's sunrise.
    tomorrow = (
        date_obj +
        timedelta(days=1)
    )

    tomorrow_text = fetch_panchang(
        tomorrow
    )

    next_sunrise, _ = extract_sun_times(
        tomorrow_text
    )

    print("Sunrise:", sunrise)
    print("Sunset :", sunset)
    print("Next sunrise:", next_sunrise)

    horas = calculate_24_horas(
        date_obj,
        sunrise,
        sunset,
        next_sunrise
    )

    market_horas = create_market_horas(
        horas,
        date_obj
    )

    return market_horas


# ============================================================
# MAIN
# ============================================================

def main():

    today = datetime.now(
        IST
    ).date()

    rows = process_date(
        today
    )

    df = pd.DataFrame(
        rows
    )

    print()
    print("=" * 70)
    print("TIRUPATI MARKET HORA")
    print("=" * 70)

    if df.empty:

        print(
            "No Hora overlaps the market window."
        )

        return

    display_columns = [
        "Date",
        "Hora",
        "Planet",
        "Hora_Start",
        "Hora_End",
        "Market_Overlap_Start",
        "Market_Overlap_End",
        "Overlap_Minutes"
    ]

    print(
        df[display_columns].to_string(
            index=False
        )
    )

    # --------------------------------------------------------
    # SAVE DAILY FILE
    # --------------------------------------------------------

    date_string = today.strftime(
        "%Y%m%d"
    )

    daily_file = (
        OUTPUT_DIR /
        f"tirupati_market_hora_{date_string}.csv"
    )

    df.to_csv(
        daily_file,
        index=False
    )

    # --------------------------------------------------------
    # ALSO UPDATE MASTER FILE
    # --------------------------------------------------------

    master_file = (
        OUTPUT_DIR /
        "tirupati_market_hora_history.csv"
    )

    if master_file.exists():

        old = pd.read_csv(
            master_file
        )

        combined = pd.concat(
            [old, df],
            ignore_index=True
        )

        combined = (
            combined
            .drop_duplicates(
                subset=[
                    "Date",
                    "Hora"
                ]
            )
            .sort_values(
                ["Date", "Hora"]
            )
        )

    else:

        combined = df

    combined.to_csv(
        master_file,
        index=False
    )

    print()
    print("Daily file:")
    print(daily_file)

    print()
    print("History file:")
    print(master_file)


if __name__ == "__main__":
    main()
