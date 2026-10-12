"""Data loading and cleaning for the India Air Quality dashboard.

Dataset: Air Quality Data in India (2015-2020), city_day.csv
Source : Central Pollution Control Board (CPCB) data, compiled on Kaggle by Vopani (Rohan Rao).
"""

from pathlib import Path

import numpy as np
import pandas as pd

DATA_PATH = Path(__file__).parent / "data" / "city_day.csv"

POLLUTANTS = ["PM2.5", "PM10", "NO", "NO2", "NOx", "NH3", "CO", "SO2", "O3",
              "Benzene", "Toluene", "Xylene"]

UNITS = {p: "µg/m³" for p in POLLUTANTS}
UNITS["CO"] = "mg/m³"
UNITS["AQI"] = "index"

# CPCB National AQI categories and their official colour convention
AQI_BUCKETS = ["Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"]
AQI_RANGES = {"Good": (0, 50), "Satisfactory": (51, 100), "Moderate": (101, 200),
              "Poor": (201, 300), "Very Poor": (301, 400), "Severe": (401, 500)}
AQI_COLORS = {"Good": "#00a65a", "Satisfactory": "#9acd32", "Moderate": "#e6c200",
              "Poor": "#f08c00", "Very Poor": "#e03131", "Severe": "#862e2e"}

SEASONS = {12: "Winter", 1: "Winter", 2: "Winter",
           3: "Summer", 4: "Summer", 5: "Summer",
           6: "Monsoon", 7: "Monsoon", 8: "Monsoon", 9: "Monsoon",
           10: "Post-monsoon", 11: "Post-monsoon"}


def aqi_to_bucket(aqi: float):
    """Map a numeric AQI value to its CPCB category."""
    if pd.isna(aqi):
        return np.nan
    for name, (_, hi) in AQI_RANGES.items():
        if aqi <= hi:
            return name
    return "Severe"


def load_data(path: Path = DATA_PATH) -> pd.DataFrame:
    """Load city_day.csv and return a cleaned DataFrame."""
    df = pd.read_csv(path)

    # 1. Types
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date", "City"])
    df["City"] = df["City"].str.strip()

    # 2. Duplicates (same city and date)
    df = df.drop_duplicates(subset=["City", "Date"], keep="first")

    # 3. Invalid values: concentrations and AQI cannot be negative
    numeric = POLLUTANTS + ["AQI"]
    df[numeric] = df[numeric].apply(pd.to_numeric, errors="coerce")
    df[numeric] = df[numeric].mask(df[numeric] < 0)

    # 4. Fill missing AQI_Bucket where AQI is present
    missing_bucket = df["AQI_Bucket"].isna() & df["AQI"].notna()
    df.loc[missing_bucket, "AQI_Bucket"] = df.loc[missing_bucket, "AQI"].map(aqi_to_bucket)

    # 5. Derived time features
    df["Year"] = df["Date"].dt.year
    df["Month"] = df["Date"].dt.month
    df["MonthName"] = df["Date"].dt.strftime("%b")
    df["Season"] = df["Month"].map(SEASONS)

    return df.sort_values(["City", "Date"]).reset_index(drop=True)


def interpolate_gaps(df: pd.DataFrame, cols, limit_days: int = 7) -> pd.DataFrame:
    """Linearly interpolate short gaps (<= limit_days) within each city.

    Long gaps are left empty so the charts do not invent data where a
    monitoring station was offline for weeks.
    """
    out = df.copy()
    out[cols] = (out.groupby("City")[cols]
                    .transform(lambda s: s.interpolate(limit=limit_days, limit_area="inside")))
    return out


def missing_summary(df: pd.DataFrame) -> pd.DataFrame:
    cols = POLLUTANTS + ["AQI"]
    s = pd.DataFrame({
        "Missing values": df[cols].isna().sum(),
        "Missing %": (df[cols].isna().mean() * 100).round(1),
    })
    return s.sort_values("Missing %", ascending=False)
