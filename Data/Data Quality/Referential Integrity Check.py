"""
Referential Integrity Check - every relationship in Data/data_model_relationships.csv

For each relationship (foreign key column -> primary key column) checks that:
  - values in the primary key field are unique (and not blank)
  - values in the foreign key field exist in the other table's primary key field

Every violation is written, one row per bad record, to
Data/Data Quality/referential_integrity_violations.csv, and a summary per check is
printed to the terminal.

Uses the clean version of a table from Data/Clean when one exists, otherwise the raw
file. Keys are normalized before matching: IDs like `45.0` become `45`, and dates in
any format are compared as calendar dates.

Run from anywhere:
    python "Data/Data Quality/Referential Integrity Check.py"
"""

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent
RELATIONSHIPS_FILE = DATA_DIR / "data_model_relationships.csv"
VIOLATIONS_FILE = Path(__file__).resolve().parent / "referential_integrity_violations.csv"

# One row per violating record in the output CSV
VIOLATION_COLUMNS = ["check", "table", "column", "references", "row_number", "record_id", "value", "issue"]

# Child columns allowed to be blank (cash movements have no security)
NULLABLE = {("fact_transactions", "security_id")}


def load_table(name):
    """Return (DataFrame, file used) preferring Clean/<name>_clean.csv over Raw/."""
    for path in (DATA_DIR / "Clean" / f"{name}_clean.csv",
                 DATA_DIR / "Raw" / f"{name}_raw.csv",
                 DATA_DIR / "Raw" / f"{name}.csv"):
        if path.exists():
            return pd.read_csv(path, dtype=str, keep_default_na=False), path
    raise FileNotFoundError(f"No file found for table {name}")


def normalize(values, column):
    """Convert key strings to comparable values. Blank or unparseable values become NaN."""
    values = values.str.strip()
    if column == "date" or column.endswith("_date"):
        return pd.to_datetime(values, format="mixed", errors="coerce").dt.date
    nums = pd.to_numeric(values, errors="coerce")
    whole = nums.notna() & (nums % 1 == 0)
    return nums.where(whole).astype("Int64")


def check_primary_key(table, df, column):
    """Return one violation row per record whose primary key is blank, unparseable or duplicated."""
    raw = df[column].str.strip()
    keys = normalize(df[column], column)
    issue = pd.Series("", index=df.index)
    issue[raw == ""] = "Primary key is blank"
    issue[(raw != "") & keys.isna()] = "Primary key is not a valid value"
    dup = keys.notna() & keys.duplicated(keep=False)
    issue[dup] = "Duplicate primary key (" + keys[dup].map(keys[dup].value_counts()).astype(str) + " rows share it)"

    bad = issue != ""
    return pd.DataFrame({
        "check": "Primary key unique",
        "table": table,
        "column": column,
        "references": "",
        "row_number": df.index[bad] + 2,  # CSV line number (header is line 1)
        "record_id": df.iloc[:, 0][bad],
        "value": raw[bad],
        "issue": issue[bad],
    }, columns=VIOLATION_COLUMNS)


def check_foreign_key(table, df, column, parent_table, parent_df, parent_column):
    """Return one violation row per record whose foreign key is missing from the parent's primary key."""
    raw = df[column].str.strip()
    keys = normalize(df[column], column)
    parent_keys = set(normalize(parent_df[parent_column], parent_column).dropna())

    issue = pd.Series("", index=df.index)
    if (table, column) not in NULLABLE:
        issue[raw == ""] = "Foreign key is blank"
    issue[(raw != "") & keys.isna()] = "Foreign key is not a valid value"
    issue[keys.notna() & ~keys.isin(parent_keys)] = f"Value not found in {parent_table}.{parent_column}"

    bad = issue != ""
    return pd.DataFrame({
        "check": "Foreign key exists",
        "table": table,
        "column": column,
        "references": f"{parent_table}.{parent_column}",
        "row_number": df.index[bad] + 2,  # CSV line number (header is line 1)
        "record_id": df.iloc[:, 0][bad],
        "value": raw[bad],
        "issue": issue[bad],
    }, columns=VIOLATION_COLUMNS)


def run_checks(relationships, tables):
    """Run each primary key check once and each foreign key check. Return (violations, summary)."""
    results, summary = [], []

    def record(check, name, found):
        results.append(found)
        summary.append({"Check": check, "Field": name, "Violations": len(found),
                        "Result": "FAIL" if len(found) else "PASS"})

    primary_keys = relationships[["to_table", "to_column"]].drop_duplicates()
    for pk in primary_keys.itertuples(index=False):
        df, _ = tables[pk.to_table]
        record("Primary key unique", f"{pk.to_table}.{pk.to_column}",
               check_primary_key(pk.to_table, df, pk.to_column))

    for rel in relationships.itertuples(index=False):
        df, _ = tables[rel.from_table]
        parent_df, _ = tables[rel.to_table]
        record("Foreign key exists", f"{rel.from_table}.{rel.from_column} -> {rel.to_table}.{rel.to_column}",
               check_foreign_key(rel.from_table, df, rel.from_column, rel.to_table, parent_df, rel.to_column))

    return pd.concat(results, ignore_index=True), pd.DataFrame(summary)


def print_table(df):
    df.insert(0, "#", range(1, len(df) + 1))
    print("| " + " | ".join(df.columns) + " |")
    print("|" + "|".join("---" for _ in df.columns) + "|")
    for r in df.itertuples(index=False):
        print("| " + " | ".join(str(v) for v in r) + " |")


def main():
    relationships = pd.read_csv(RELATIONSHIPS_FILE)
    names = sorted(set(relationships.from_table) | set(relationships.to_table))
    tables = {name: load_table(name) for name in names}

    print("Referential Integrity Check")
    print("Files used:")
    for name in names:
        print(f"  {name}: {tables[name][1].relative_to(DATA_DIR)}")
    print()

    violations, summary = run_checks(relationships, tables)
    print_table(summary)

    violations.to_csv(VIOLATIONS_FILE, index=False)
    fails = (summary.Result == "FAIL").sum()
    print(f"\n{len(summary) - fails} passed, {fails} failed, {len(violations)} violating records")
    print(f"Violations written to {VIOLATIONS_FILE.relative_to(DATA_DIR.parent)}")


if __name__ == "__main__":
    main()
