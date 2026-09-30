"""
Clean Client Data - dim_client_raw.csv -> dim_client_clean.csv

Fixes the data quality issues reported by Data/Data Quality/Data Quality Errors.py,
one function per issue, applied in order. Each step prints how many rows it changed.

Always reads the untouched raw file and overwrites the clean file, so it is safe
to re-run after changing a step.

Run from anywhere:
    python "Data/Clean/Clean Client Data.py"
"""

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent
RAW_FILE = DATA_DIR / "Raw" / "dim_client_raw.csv"
CLEAN_FILE = DATA_DIR / "Clean" / "dim_client_clean.csv"

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

VALID_AGE = (18, 110)
IS_ACTIVE_MAP = {"True": "True", "yes": "True", "False": "False", "0": "False"}
MISSING_RISK = "Unknown"


# 1. Duplicate IDs: the repeated rows match the original except for a garbled last_name
def remove_duplicate_ids(df):
    dup = df.client_id.duplicated(keep="first")
    return df[~dup].reset_index(drop=True), dup.sum()


# 2. Garbled last names: all were in the duplicate rows, so step 1 removes them.
#    This step only checks that none are left; it does not guess at the correct spelling.
def check_garbled_last_names(df):
    bad = df.last_name.str.contains(r"[^A-Za-z\s'\-\.]", regex=True)
    if bad.any():
        print(f"    WARNING: {bad.sum()} garbled last names remain: {list(df.last_name[bad].head())}")
    return df, 0


# 3. City: trim spaces and convert ALL CAPS to title case
def fix_city(df):
    fixed = df.city.str.strip()
    fixed = fixed.where(~fixed.str.isupper(), fixed.str.title())
    changed = (fixed != df.city).sum()
    return df.assign(city=fixed), changed


# 4. State: full names -> 2-letter codes
def fix_state(df):
    fixed = df.state.replace(STATE_NAMES)
    return df.assign(state=fixed), (fixed != df.state).sum()


# 5. ZIP code: restore leading zeros dropped by numeric conversion
def fix_zip_code(df):
    fixed = df.zip_code.str.zfill(5)
    return df.assign(zip_code=fixed), (fixed != df.zip_code).sum()


# 6. Age: impossible values (0, -5, 999) are blanked; the true age cannot be recovered
def fix_age(df):
    age = pd.to_numeric(df.age, errors="coerce")
    bad = age.isna() | (age < VALID_AGE[0]) | (age > VALID_AGE[1])
    return df.assign(age=df.age.mask(bad, "")), bad.sum()


# 7. Risk profile: blanks are random and cannot be predicted, so label them explicitly
def fix_risk_profile(df):
    blank = df.risk_profile.str.strip() == ""
    return df.assign(risk_profile=df.risk_profile.mask(blank, MISSING_RISK)), blank.sum()


# 8. is_active: map yes/0 onto a single True/False encoding
def fix_is_active(df):
    fixed = df.is_active.map(IS_ACTIVE_MAP)
    if fixed.isna().any():
        raise ValueError(f"Unexpected is_active values: {df.is_active[fixed.isna()].unique()}")
    return df.assign(is_active=fixed), (fixed != df.is_active).sum()


# 9. client_since: convert MM/DD/YYYY to ISO YYYY-MM-DD
def fix_client_since(df):
    iso = pd.to_datetime(df.client_since, format="%Y-%m-%d", errors="coerce")
    us = pd.to_datetime(df.client_since, format="%m/%d/%Y", errors="coerce")
    parsed = iso.fillna(us)
    if parsed.isna().any():
        raise ValueError(f"Unparseable client_since values: {df.client_since[parsed.isna()].unique()}")
    fixed = parsed.dt.strftime("%Y-%m-%d")
    return df.assign(client_since=fixed), (fixed != df.client_since).sum()


# Issues 10-12 from the report are left as-is on purpose:
#   10. initial_aum skew       - real UHNW balances, not an error
#   11. ZIP / state mismatch   - cannot be fixed from this file
#   12. Onboarded as minors    - low confidence, depends on the snapshot date
STEPS = [
    ("Remove duplicate client_ids", remove_duplicate_ids),
    ("Check garbled last names", check_garbled_last_names),
    ("Trim and title-case city", fix_city),
    ("Convert state names to codes", fix_state),
    ("Pad ZIP codes to 5 digits", fix_zip_code),
    ("Blank impossible ages", fix_age),
    (f"Fill blank risk_profile with '{MISSING_RISK}'", fix_risk_profile),
    ("Standardize is_active to True/False", fix_is_active),
    ("Convert client_since to YYYY-MM-DD", fix_client_since),
]


def main():
    df = pd.read_csv(RAW_FILE, dtype=str, keep_default_na=False)
    print(f"Cleaning {RAW_FILE.name}: {len(df)} rows x {len(df.columns)} columns\n")

    for i, (name, step) in enumerate(STEPS, 1):
        df, changed = step(df)
        print(f"{i}. {name}: {changed} rows changed")

    df.to_csv(CLEAN_FILE, index=False)
    print(f"\nSaved {len(df)} rows to {CLEAN_FILE}")


if __name__ == "__main__":
    main()
