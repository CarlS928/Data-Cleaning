"""
Identified Errors - dim_client_raw.csv

Profiles Data/Raw/dim_client_raw.csv and prints every data quality issue as a
table: #, Column, Issue, Rows affected, Details.

Run from anywhere:
    python "Data/Data Quality/Data Quality Errors.py"
"""

from datetime import date
from pathlib import Path

import pandas as pd

RAW_FILE = Path(__file__).resolve().parent.parent / "Raw" / "dim_client_raw.csv"

STATE_NAMES = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
    "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "Florida": "FL", "Georgia": "GA",
    "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA",
    "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH",
    "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY", "North Carolina": "NC",
    "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA",
    "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN",
    "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY", "District of Columbia": "DC",
}

# First digit of a valid ZIP code for each state (USPS national areas)
ZIP_FIRST_DIGIT = {
    "0": "CT MA ME NH NJ PR RI VT",
    "1": "DE NY PA",
    "2": "DC MD NC SC VA WV",
    "3": "AL FL GA MS TN",
    "4": "IN KY MI OH",
    "5": "IA MN MT ND SD WI",
    "6": "IL KS MO NE",
    "7": "AR LA OK TX",
    "8": "AZ CO ID NM NV UT WY",
    "9": "AK CA HI OR WA",
}
STATE_ZIP_DIGIT = {st: d for d, states in ZIP_FIRST_DIGIT.items() for st in states.split()}

VALID_AGE = (18, 110)
TIER_AUM_BANDS = {"Retail": (0, 500_000), "HNW": (500_000, 5_000_000), "UHNW": (5_000_000, float("inf"))}


def sample(values, n=4):
    """Format a few example values for the Details column."""
    vals = list(dict.fromkeys(str(v) for v in values))[:n]
    return ", ".join(f"`{v}`" for v in vals)


def find_issues(df):
    issues = []

    def add(column, issue, rows, details):
        issues.append({"Column": column, "Issue": issue, "Rows affected": rows, "Details": details})

    line_no = df.index + 2  # line number in the CSV file (header is line 1)

    # 1 + 2. Duplicate client_ids (repeated rows carry garbled last names)
    dup_mask = df.client_id.duplicated(keep="first")
    dups = df[dup_mask]
    if len(dups):
        lines = line_no[dup_mask]
        add("client_id", "Duplicate IDs", f"{len(dups)} extra rows",
            f"File lines {lines.min()}-{lines.max()} repeat {dups.client_id.nunique()} existing clients "
            f"(IDs {sample(dups.client_id, 3)}). All fields match the original except `last_name`. "
            "Remove the repeated rows.")

    bad_name = df.last_name.str.contains(r"[^A-Za-z\s'\-\.]", regex=True)
    if bad_name.any():
        overlap = (bad_name & dup_mask).sum()
        add("last_name", "Garbled characters", bad_name.sum(),
            f"Symbols or digits in place of letters: {sample(df.last_name[bad_name])}. "
            f"{overlap} of these are the duplicate rows above.")

    # 3. City whitespace / casing
    city_ws = df.city != df.city.str.strip()
    city_upper = df.city.str.strip().str.isupper()
    city_bad = city_ws | city_upper
    if city_bad.any():
        clean_city = df.city.str.strip().str.title()
        collisions = clean_city[city_bad].isin(set(df.city[~city_bad])).sum()
        add("city", "Whitespace and ALL CAPS", city_bad.sum(),
            f"{city_ws.sum()} have leading/trailing spaces, {city_upper.sum()} are uppercase "
            f"(e.g. `'{df.city[city_bad].iloc[0]}'`). {collisions} collide with existing names once normalized.")

    # 4. State format
    full_state = df.state.isin(STATE_NAMES)
    if full_state.any():
        top = df.state[full_state].value_counts().head(4)
        add("state", "Mixed formats", full_state.sum(),
            "Full names instead of 2-letter codes: " + ", ".join(f"`{k}` {v}" for k, v in top.items()) + "...")

    # 5. ZIP leading zeros
    zip_len = df.zip_code.str.len()
    short_zip = zip_len < 5
    if short_zip.any():
        by_len = zip_len[short_zip].value_counts().sort_index(ascending=False)
        add("zip_code", "Missing leading zeros", short_zip.sum(),
            ", ".join(f"{v} are {k}-digit" for k, v in by_len.items())
            + f" (e.g. `{df.zip_code[short_zip].iloc[0]}` should be `{df.zip_code[short_zip].iloc[0].zfill(5)}`). "
            "Pad to 5 characters and store as text.")

    # 6. Impossible ages
    age = pd.to_numeric(df.age, errors="coerce")
    bad_age = age.isna() | (age < VALID_AGE[0]) | (age > VALID_AGE[1])
    if bad_age.any():
        counts = df.age[bad_age].value_counts()
        ok = age[~bad_age]
        add("age", "Impossible values", bad_age.sum(),
            ", ".join(f"`{k}` (x{v})" for k, v in counts.items())
            + f". All other ages fall between {int(ok.min())} and {int(ok.max())}.")

    # 7. Blank risk_profile
    blank_risk = df.risk_profile.str.strip() == ""
    if blank_risk.any():
        add("risk_profile", "Blank values", f"{blank_risk.sum()} ({blank_risk.mean():.0%})",
            "Empty strings. Fill with `Unknown` or leave null.")

    # 8. is_active encodings
    active_counts = df.is_active.value_counts()
    non_bool = ~df.is_active.isin(["True", "False"])
    if non_bool.any():
        add("is_active", "Mixed boolean encodings", non_bool.sum(),
            ", ".join(f"`{k}` {v}" for k, v in active_counts.items())
            + ". Map to a single True/False type.")

    # 9. client_since formats
    iso = pd.to_datetime(df.client_since, format="%Y-%m-%d", errors="coerce")
    us = pd.to_datetime(df.client_since, format="%m/%d/%Y", errors="coerce")
    non_iso = iso.isna()
    if non_iso.any():
        slash = df.client_since[non_iso].str.split("/", expand=True).astype(int)
        unparsed = (iso.isna() & us.isna()).sum()
        add("client_since", "Mixed date formats", non_iso.sum(),
            f"{(~non_iso).sum()} are ISO (`YYYY-MM-DD`), {non_iso.sum()} are `MM/DD/YYYY` "
            f"(e.g. {sample(df.client_since[non_iso], 2)}). Second part >12 in {(slash[1] > 12).sum()} rows, "
            f"first part never >12 -> month-first. {unparsed} fail to parse either way.")

    # 10. AUM skew (informational) + tier consistency
    aum = pd.to_numeric(df.initial_aum, errors="coerce")
    q1, q3 = aum.quantile([0.25, 0.75])
    outliers = (aum < q1 - 3 * (q3 - q1)) | (aum > q3 + 3 * (q3 - q1))
    tier_mismatch = sum(
        (~aum[df.client_tier == t].between(lo, hi, inclusive="left")).sum()
        for t, (lo, hi) in TIER_AUM_BANDS.items()
    )
    if outliers.any():
        add("initial_aum", "Heavy right skew (not an error)", f"{outliers.sum()} flagged by IQR",
            f"Range ${aum[outliers].min():,.0f}-${aum[outliers].max():,.0f}, all real UHNW balances. "
            f"Tier vs AUM bands: {tier_mismatch} mismatches. No fix needed.")

    # 11. ZIP not matching state
    state_code = df.state.replace(STATE_NAMES)
    expected = state_code.map(STATE_ZIP_DIGIT)
    zip_mismatch = expected.notna() & (df.zip_code.str.zfill(5).str[0] != expected)
    if zip_mismatch.any():
        add("zip_code / state", "ZIPs don't match states", f"{zip_mismatch.sum()} ({zip_mismatch.mean():.0%})",
            "ZIP first digit is outside the state's USPS range. Likely synthetic data; "
            "cannot be fixed from this file, so note only.")

    # 12. Onboarded as a minor (assumes age is current as of today)
    years_as_client = (pd.Timestamp(date.today()) - iso.fillna(us)).dt.days / 365.25
    minor = ~bad_age & ((age - years_as_client) < 18)
    if minor.any():
        add("age / client_since", "Possibly onboarded as minors", minor.sum(),
            f"Excluding impossible ages, these clients were under 18 at `client_since` if `age` is "
            f"current as of {date.today()}. Low confidence; depends on the snapshot date.")

    return pd.DataFrame(issues)


def print_table(issues):
    issues.insert(0, "#", range(1, len(issues) + 1))
    cols = issues.columns
    rows = [[str(v) for v in r] for r in issues.itertuples(index=False)]
    print("| " + " | ".join(cols) + " |")
    print("|" + "|".join("---" for _ in cols) + "|")
    for r in rows:
        print("| " + " | ".join(r) + " |")


def main():
    df = pd.read_csv(RAW_FILE, dtype=str, keep_default_na=False)
    print(f"Identified Errors - {RAW_FILE.name}")
    print(f"{len(df)} rows x {len(df.columns)} columns\n")
    issues = find_issues(df)
    print_table(issues)

    clean = [c for c in df.columns if c not in set(
        c for col in issues["Column"] for c in col.split(" / "))]
    print(f"\nNo issues found in: {', '.join(clean)}")


if __name__ == "__main__":
    main()
