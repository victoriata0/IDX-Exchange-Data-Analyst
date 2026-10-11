"""
Weeks 2–3 (continued) – Mortgage Rate Enrichment
(1) Fetches the FRED MORTGAGE30US series (30-yr fixed, weekly, Freddie Mac)
(2) Resamples weekly -> monthly average
(3) Merges onto the sold and listings datasets on a year_month key
    - sold:     year_month from CloseDate
    - listings: year_month from ListingContractDate
(4) Validates that no rate values are null after the merge
Then saves both enriched datasets.

Inputs:  output/sold_residential_filtered.csv      (from week2_3_eda.py)
         output/listings_residential_filtered.csv
Outputs: output/sold_with_rates.csv
         output/listings_with_rates.csv
         output/mortgage30us_monthly.csv

If the FRED download is blocked on your network, download the CSV manually
from https://fred.stlouisfed.org/series/MORTGAGE30US (Download -> CSV), save it
as MORTGAGE30US.csv in the Internship folder, and re-run.
"""
import io
from pathlib import Path
import pandas as pd
import requests

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "output"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=MORTGAGE30US"
LOCAL_FALLBACK = BASE / "MORTGAGE30US.csv"

# 1. Fetch the mortgage rate data from FRED (no API key needed)
try:
    # Download with requests (bundles its own SSL certificates via certifi) –
    # pd.read_csv(url) can fail on python.org installs on macOS with
    # CERTIFICATE_VERIFY_FAILED.
    resp = requests.get(FRED_URL, timeout=60)
    resp.raise_for_status()
    mortgage = pd.read_csv(io.StringIO(resp.text))
    print(f"Fetched MORTGAGE30US from FRED: {len(mortgage):,} weekly observations")
except Exception as e:
    print(f"FRED fetch failed ({type(e).__name__}); trying local {LOCAL_FALLBACK.name}")
    mortgage = pd.read_csv(LOCAL_FALLBACK)

# FRED has used both 'observation_date' and 'DATE' as the date header
mortgage.columns = ["date", "rate_30yr_fixed"]
mortgage["date"] = pd.to_datetime(mortgage["date"])
mortgage["rate_30yr_fixed"] = pd.to_numeric(mortgage["rate_30yr_fixed"], errors="coerce")
mortgage = mortgage.dropna(subset=["rate_30yr_fixed"])
print(f"Weekly range: {mortgage['date'].min():%Y-%m-%d} -> {mortgage['date'].max():%Y-%m-%d}")

# 2. – Resample weekly rates to monthly averages
mortgage["year_month"] = mortgage["date"].dt.to_period("M")
mortgage_monthly = (
    mortgage.groupby("year_month")["rate_30yr_fixed"]
    .mean()
    .round(3)
    .reset_index()
)
mortgage_monthly.to_csv(OUT / "mortgage30us_monthly.csv", index=False)
print("\nMonthly averages, Jan 2024 onward:")
print(mortgage_monthly[mortgage_monthly["year_month"] >= "2024-01"].to_string(index=False))

# 3. Load MLS data and create the matching year_month key
sold = pd.read_csv(OUT / "sold_residential_filtered.csv", low_memory=False)
listings = pd.read_csv(OUT / "listings_residential_filtered.csv", low_memory=False)

# Sold dataset — key off CloseDate
sold["year_month"] = pd.to_datetime(sold["CloseDate"], errors="coerce").dt.to_period("M")
# Listings dataset — key off ListingContractDate
listings["year_month"] = pd.to_datetime(
    listings["ListingContractDate"], errors="coerce"
).dt.to_period("M")

# 4. Merge (left join keeps every MLS row)
sold_with_rates = sold.merge(mortgage_monthly, on="year_month", how="left")
listings_with_rates = listings.merge(mortgage_monthly, on="year_month", how="left")

# 5. Validate the merge
print("\nValidation:")
for name, before, after in (("sold", sold, sold_with_rates),
                            ("listings", listings, listings_with_rates)):
    nulls = after["rate_30yr_fixed"].isnull().sum()
    print(f"  {name:9s} rows before={len(before):,} after={len(after):,} "
          f"| null rate values: {nulls}")
    # A left join on a unique monthly key must not add or drop rows
    assert len(before) == len(after), f"{name}: row count changed in merge"
    if nulls:
        bad = after.loc[after["rate_30yr_fixed"].isnull(), "year_month"].value_counts(dropna=False)
        print(f"    unmatched year_month values:\n{bad.to_string()}")
    assert nulls == 0, f"{name}: {nulls} rows have no mortgage rate"
print("  ✓ No null rate values in either dataset")

print("\nPreview:")
print(sold_with_rates[["CloseDate", "year_month", "ClosePrice", "rate_30yr_fixed"]].head())

# Save
sold_with_rates.to_csv(OUT / "sold_with_rates.csv", index=False)
listings_with_rates.to_csv(OUT / "listings_with_rates.csv", index=False)
print("\nSaved: output/sold_with_rates.csv, output/listings_with_rates.csv")
