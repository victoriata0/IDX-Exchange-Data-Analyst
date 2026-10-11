"""
Week 1 – Monthly Dataset Aggregation
January 2024 - Apr 2026 into two combined datasets (listings and
sold), filters both to PropertyType == 'Residential', and saves them as CSVs.

Run from anywhere:   python3 scripts/week1_combine.py
Inputs:  CRMLSListingYYYYMM.csv / CRMLSSoldYYYYMM.csv (or *_filled.csv) in the
         Internship folder (one level above this script)
Outputs: output/combined_listings_residential.csv
         output/combined_sold_residential.csv
"""
from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = DATA_DIR / "output"
OUT_DIR.mkdir(exist_ok=True)

#  1. Build the month range: Jan 2024 -> last completed calendar month
START = pd.Period("2024-01", freq="M")
# Data was provided through April 2026
END = max(pd.Period(f.stem[len(pfx):len(pfx) + 6], freq="M")
          for pfx in ("CRMLSSold", "CRMLSListing")
          for f in DATA_DIR.glob(f"{pfx}2*.csv"))
MONTHS = [p.strftime("%Y%m") for p in pd.period_range(START, END, freq="M")]
print(f"Target range: {MONTHS[0]} -> {MONTHS[-1]} ({len(MONTHS)} months)\n")


def find_file(prefix: str, ym: str):
    """Return the monthly file for a prefix/month. Some sold months on the FTP
    are named *_filled.csv (lat/lon back-filled); prefer that version."""
    for name in (f"{prefix}{ym}_filled.csv", f"{prefix}{ym}.csv"):
        p = DATA_DIR / name
        if p.exists():
            return p
    return None


def looks_truncated(path: Path) -> bool:
    """A complete CSV ends with a newline. A file cut off mid-download
    (e.g. an interrupted FTP transfer) usually doesn't."""
    with open(path, "rb") as fh:
        fh.seek(-1, 2)
        return fh.read(1) != b"\n"


def load_months(prefix: str) -> pd.DataFrame:
    frames, missing, truncated = [], [], []
    for ym in MONTHS:
        path = find_file(prefix, ym)
        if path is None:
            missing.append(ym)
            continue
        if looks_truncated(path):
            truncated.append(path.name)
        df = pd.read_csv(path, low_memory=False)

        # The listing extraction script requests some fields twice, so pandas
        # reads them as e.g. 'ListPrice' and 'ListPrice.1'. Drop the copies.
        dup_cols = [c for c in df.columns if c.endswith(".1") and c[:-2] in df.columns]
        df = df.drop(columns=dup_cols)

        df["source_file"] = path.name
        print(f"  {path.name:30s} {len(df):>7,} rows")
        frames.append(df)

    if missing:
        print(f"  !! MISSING months for {prefix}: {', '.join(missing)}")
    if truncated:
        print(f"  !! POSSIBLY TRUNCATED (re-download): {', '.join(truncated)}")

    # pd.concat aligns on column names; columns that exist in only some months
    # (e.g. latfilled/lonfilled in the *_filled sold files) are NaN elsewhere.
    return pd.concat(frames, ignore_index=True)


# 2. Concatenate
print("Loading LISTING files...")
listings = load_months("CRMLSListing")
print(f"Combined listings (all property types): {len(listings):,} rows, {listings.shape[1]} cols\n")

print("Loading SOLD files...")
sold = load_months("CRMLSSold")
print(f"Combined sold (all property types): {len(sold):,} rows, {sold.shape[1]} cols\n")

# 3. Filter to Residential only
listings_res = listings[listings["PropertyType"] == "Residential"].copy()
sold_res = sold[sold["PropertyType"] == "Residential"].copy()

print(f"Listings: {len(listings):,} -> {len(listings_res):,} after Residential filter "
      f"({len(listings_res) / len(listings):.1%} kept)")
print(f"Sold:     {len(sold):,} -> {len(sold_res):,} after Residential filter "
      f"({len(sold_res) / len(sold):.1%} kept)")

# 4. Save
listings_res.to_csv(OUT_DIR / "combined_listings_residential.csv", index=False)
sold_res.to_csv(OUT_DIR / "combined_sold_residential.csv", index=False)
print(f"\nSaved to {OUT_DIR}")

# ROW COUNT LOG  (run on 2026-10-11, Jan 2024 – Apr 2026, 56 files)
# Before concatenation (per-file rows, all property types):
#   Listings: 28 monthly files, 18,773 (202512) ... 40,271 (202505) per month
#   Sold:     28 monthly files, 16,487 (202601) ... 26,487 (202405) per month
#
# After concatenation (all property types):
#   Listings: 872,785 rows  (74 cols after dropping 11 duplicate '.1' cols)
#   Sold:     615,707 rows  (85 cols)
#
# After Residential filter:
#   Listings: 872,785 -> 557,051 rows (63.8% kept)
#   Sold:     615,707 -> 414,054 rows (67.2% kept)
#
# Note: CRMLSListing202401 / 202403 / 202601 were re-extracted from the Trestle
# API (crmls_extract.py) on 2026-10-11 after the FTP copies were found truncated.
