"""
Clean Data Quality Check - dim_client_clean.csv

Validates Data/Clean/dim_client_clean.csv against the rules the cleaning script
is meant to enforce, and prints a PASS / FAIL / NOTE table:
#, Column, Check, Result, Rows failing, Details.

FAIL means the clean file still has a problem. NOTE is informational (known
limitations that were left as-is on purpose). Exits with code 1 if anything fails.

Run from anywhere:
    python "Data/Data Quality/Clean Data Quality Check.py"
"""

import sys
from datetime import date
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent
CLEAN_FILE = DATA_DIR / "Clean" / "dim_client_clean.csv"
RAW_FILE = DATA_DIR / "Raw" / "dim_client_raw.csv"
ADVISOR_FILE = DATA_DIR / "Raw" / "dim_advisor_raw.csv"

EXPECTED_COLUMNS = [
    "client_id", "first_name", "last_name", "age", "city", "state", "zip_code", "risk_profile",
    "client_tier", "primary_account_type", "initial_aum", "client_since", "advisor_id", "is_active",
]
STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS",
    "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY",
    "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC",
}
RISK_PROFILES = {"Conservative", "Moderately Conservative", "Balanced", "Moderately Aggressive",
                 "Aggressive", "Unknown"}
CLIENT_TIERS = {"Retail", "HNW", "UHNW"}
ACCOUNT_TYPES = {"529", "IRA", "Roth IRA", "Taxable", "Trust"}
VALID_AGE = (18, 110)
TIER_AUM_BANDS = {"Retail": (0, 500_000), "HNW": (500_000, 5_000_000), "UHNW": (5_000_000, float("inf"))}
# Columns allowed to contain blanks (impossible ages were blanked on purpose)
BLANKS_ALLOWED = {"age"}


def sample(values, n=4):
    """Format a few example values for the Details column."""
    vals = list(dict.fromkeys(str(v) for v in values))[:n]
    return ", ".join(f"`{v}`" for v in vals)


def run_checks(df):
    results = []

    def check(column, name, failing, ok_details="", fail_details=""):
        """failing: boolean Series of rows that break the rule."""
        n = int(failing.sum())
        results.append({
            "Column": column, "Check": name, "Result": "FAIL" if n else "PASS",
            "Rows failing": n, "Details": fail_details(df[failing]) if n else ok_details,
        })

    def note(column, name, count, details):
        results.append({"Column": column, "Check": name, "Result": "NOTE",
                        "Rows failing": count, "Details": details})

    # Structure
    missing_cols = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    extra_cols = [c for c in df.columns if c not in EXPECTED_COLUMNS]
    results.append({
        "Column": "(all)", "Check": "Expected columns", "Result": "FAIL" if missing_cols or extra_cols else "PASS",
        "Rows failing": 0, "Details": f"Missing {missing_cols}, extra {extra_cols}" if missing_cols or extra_cols
        else f"All {len(EXPECTED_COLUMNS)} columns present",
    })
    if missing_cols:
        return pd.DataFrame(results)

    raw = pd.read_csv(RAW_FILE, dtype=str, keep_default_na=False)
    raw_ids = set(raw.client_id)
    results.append({
        "Column": "client_id", "Check": "One row per raw client", "Rows failing": abs(len(df) - len(raw_ids)),
        "Result": "PASS" if len(df) == len(raw_ids) and set(df.client_id) == raw_ids else "FAIL",
        "Details": f"{len(df)} rows vs {len(raw_ids)} unique IDs in raw file",
    })

    blank = df.apply(lambda s: s.str.strip() == "")
    for col in df.columns:
        if col in BLANKS_ALLOWED:
            note(col, "Blank values (allowed)", int(blank[col].sum()),
                 "Impossible ages blanked during cleaning; true age unknown.")
        else:
            check(col, "No blank values", blank[col], "No blanks",
                  lambda bad: f"{len(bad)} blank")

    # Per-column rules
    check("client_id", "Unique", df.client_id.duplicated(keep=False), "All unique",
          lambda bad: f"Duplicated IDs: {sample(bad.client_id)}")
    check("client_id", "Positive integer", ~df.client_id.str.fullmatch(r"[1-9]\d*"), "All positive integers",
          lambda bad: sample(bad.client_id))

    for col in ["first_name", "last_name"]:
        check(col, "Letters only", ~df[col].str.fullmatch(r"[A-Za-z][A-Za-z\s'\-\.]*"), "No symbols or digits",
              lambda bad, col=col: sample(bad[col]))

    age = pd.to_numeric(df.age, errors="coerce")
    check("age", f"Between {VALID_AGE[0]} and {VALID_AGE[1]} (or blank)",
          ~blank.age & ~age.between(*VALID_AGE),
          f"Range {int(age.min())}-{int(age.max())}", lambda bad: sample(bad.age))

    check("city", "No leading/trailing spaces", df.city != df.city.str.strip(), "Trimmed",
          lambda bad: sample(bad.city.map(repr)))
    check("city", "Not ALL CAPS", df.city.str.isupper(), "No all-caps names",
          lambda bad: sample(bad.city))

    check("state", "Valid 2-letter code", ~df.state.isin(STATE_CODES), f"{df.state.nunique()} states, all codes",
          lambda bad: sample(bad.state))
    check("zip_code", "Exactly 5 digits", ~df.zip_code.str.fullmatch(r"\d{5}"), "All 5 digits",
          lambda bad: sample(bad.zip_code))

    check("risk_profile", "Allowed value", ~df.risk_profile.isin(RISK_PROFILES), "All allowed values",
          lambda bad: sample(bad.risk_profile))
    unknown = (df.risk_profile == "Unknown").sum()
    note("risk_profile", "Unknown (filled blanks)", int(unknown),
         f"{unknown / len(df):.0%} of clients have no risk profile on file.")

    check("client_tier", "Allowed value", ~df.client_tier.isin(CLIENT_TIERS), "Retail / HNW / UHNW",
          lambda bad: sample(bad.client_tier))
    check("primary_account_type", "Allowed value", ~df.primary_account_type.isin(ACCOUNT_TYPES),
          ", ".join(sorted(ACCOUNT_TYPES)), lambda bad: sample(bad.primary_account_type))

    aum = pd.to_numeric(df.initial_aum, errors="coerce")
    check("initial_aum", "Numeric and positive", aum.isna() | (aum <= 0),
          f"Range ${aum.min():,.0f}-${aum.max():,.0f}", lambda bad: sample(bad.initial_aum))
    tier_bad = pd.Series(False, index=df.index)
    for tier, (lo, hi) in TIER_AUM_BANDS.items():
        in_tier = df.client_tier == tier
        tier_bad |= in_tier & ~aum.between(lo, hi, inclusive="left")
    check("client_tier / initial_aum", "AUM within tier band", tier_bad, "All clients within their tier's band",
          lambda bad: sample(bad.client_id + ":" + bad.client_tier))

    since = pd.to_datetime(df.client_since, format="%Y-%m-%d", errors="coerce")
    check("client_since", "Valid YYYY-MM-DD date", ~df.client_since.str.fullmatch(r"\d{4}-\d{2}-\d{2}") | since.isna(),
          f"Range {since.min():%Y-%m-%d} to {since.max():%Y-%m-%d}", lambda bad: sample(bad.client_since))
    check("client_since", "Not in the future", since > pd.Timestamp(date.today()), "No future dates",
          lambda bad: sample(bad.client_since))

    advisors = set(pd.read_csv(ADVISOR_FILE, dtype=str, keep_default_na=False).advisor_id)
    check("advisor_id", "Exists in dim_advisor", ~df.advisor_id.isin(advisors),
          f"All match the {len(advisors)} advisors", lambda bad: sample(bad.advisor_id))

    check("is_active", "True or False", ~df.is_active.isin(["True", "False"]),
          f"True {(df.is_active == 'True').sum()}, False {(df.is_active == 'False').sum()}",
          lambda bad: sample(bad.is_active))

    # Known limitations left as-is during cleaning
    note("zip_code / state", "ZIP matches state (not fixable)", None,
         "Most ZIPs fall outside their state's USPS range in the source data. See Data Quality Errors.py #11.")
    years_as_client = (pd.Timestamp(date.today()) - since).dt.days / 365.25
    minors = int(((age - years_as_client) < 18).sum())
    note("age / client_since", "Possibly onboarded as minors", minors,
         f"Low confidence; assumes age is current as of {date.today()}.")

    return pd.DataFrame(results)


def print_table(results):
    results.insert(0, "#", range(1, len(results) + 1))
    results["Rows failing"] = results["Rows failing"].map(lambda v: "-" if pd.isna(v) else str(int(v)))
    cols = results.columns
    print("| " + " | ".join(cols) + " |")
    print("|" + "|".join("---" for _ in cols) + "|")
    for r in results.itertuples(index=False):
        print("| " + " | ".join(str(v) for v in r) + " |")


def main():
    df = pd.read_csv(CLEAN_FILE, dtype=str, keep_default_na=False)
    print(f"Data Quality Check - {CLEAN_FILE.name}")
    print(f"{len(df)} rows x {len(df.columns)} columns\n")
    results = run_checks(df)
    print_table(results)

    counts = results.Result.value_counts()
    print(f"\n{counts.get('PASS', 0)} passed, {counts.get('FAIL', 0)} failed, {counts.get('NOTE', 0)} notes")
    sys.exit(1 if counts.get("FAIL", 0) else 0)


if __name__ == "__main__":
    main()
