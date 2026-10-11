"""
Weeks 2–3 – Dataset Structuring, Validation & EDA
Input:   output/combined_sold_residential.csv      (from week1_combine.py)
         output/combined_listings_residential.csv
         raw monthly CRMLS*.csv files (PropertyType column only, for type share)
Outputs: output/eda/
    property_type_counts.csv          unique property types + share (pre-filter)
    null_summary_sold.csv             null count / % per column, >90% flag
    null_summary_listings.csv
    numeric_summary_sold.csv          min/max/mean/median/percentiles + outliers
    plots/<field>.png                 histogram + boxplot per numeric field
    county_median_price.csv
    eda_report.txt                    everything printed below
    ../sold_residential_filtered.csv  sold dataset after column drop decisions
    ../listings_residential_filtered.csv
"""
from pathlib import Path
import sys
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = Path(__file__).resolve().parent.parent

# If this is a copy (e.g. github_upload/scripts), the data is one folder further up
if not any(BASE.glob("CRMLS*.csv")) and any(BASE.parent.glob("CRMLS*.csv")):
    BASE = BASE.parent
OUT = BASE / "output"
EDA = OUT / "eda"
PLOTS = EDA / "plots"
PLOTS.mkdir(parents=True, exist_ok=True)


class Tee:
    """Print to the console and to eda_report.txt at the same time."""
    def __init__(self, path):
        self.file = open(path, "w")
        self.stdout = sys.stdout
    def write(self, s):
        self.stdout.write(s); self.file.write(s)
    def flush(self):
        self.stdout.flush(); self.file.flush()

sys.stdout = Tee(EDA / "eda_report.txt")
pd.set_option("display.width", 160, "display.max_rows", 200, "display.max_columns", 20)


def section(title):
    print(f"\n{title}")


# 1. PROPERTY TYPES & FILTERING LOGIC
section("1. PROPERTY TYPES FOUND (raw monthly files, before filtering)")
rows = []
for kind in ("Sold", "Listing"):
    for f in sorted(BASE.glob(f"CRMLS{kind}2*.csv")):
        pt = pd.read_csv(f, usecols=["PropertyType"])["PropertyType"]
        rows.append(pt.value_counts().rename(kind))
types = pd.concat(rows, axis=1).T.groupby(level=0).sum().T.fillna(0).astype(int)
types["Sold_%"] = (types["Sold"] / types["Sold"].sum() * 100).round(2)
types["Listing_%"] = (types["Listing"] / types["Listing"].sum() * 100).round(2)
types = types.sort_values("Sold", ascending=False)
print(types.to_string())
types.to_csv(EDA / "property_type_counts.csv")

print("""
Filtering logic applied (week1_combine.py):
    sold     = sold[sold['PropertyType'] == 'Residential']
    listings = listings[listings['PropertyType'] == 'Residential']
Only 'Residential' (single-family / condo / townhome for sale) is kept.
Excluded: ResidentialLease (rentals), ResidentialIncome (multi-unit investment),
Land, ManufacturedInPark, Commercial*, BusinessOpportunity – these price on
different fundamentals and would distort for-sale home price analysis.
Only exact matches of 'Residential' are kept, so any malformed value
(e.g. from a truncated download) is excluded automatically.""")

# 2. LOAD FILTERED DATA & STRUCTURE
sold = pd.read_csv(OUT / "combined_sold_residential.csv", low_memory=False)
listings = pd.read_csv(OUT / "combined_listings_residential.csv", low_memory=False)

section("2. DATASET STRUCTURE")
for name, df in (("SOLD", sold), ("LISTINGS", listings)):
    print(f"{name}: {df.shape[0]:,} rows x {df.shape[1]} columns")
    print(f"  PropertyType values after filter: {df['PropertyType'].unique().tolist()}")
print("\nSold column data types:")
print(sold.dtypes.value_counts().to_string())
print()
print(sold.dtypes.to_string())

# Market-analysis fields vs. metadata / administrative fields
METADATA = [c for c in sold.columns if any(k in c for k in (
    "Agent", "Office", "AOR", "ListingKey", "ListingId", "Originating",
    "MlsStatus", "source_file", "filled", "BusinessType", "BuilderName"))]
MARKET = [c for c in sold.columns if c not in METADATA]
print(f"\nMarket-analysis fields ({len(MARKET)}): {MARKET}")
print(f"\nMetadata fields ({len(METADATA)}): {METADATA}")

# 3. MISSING VALUE ANALYSIS
CORE = ["ClosePrice", "ListPrice", "OriginalListPrice", "LivingArea", "LotSizeAcres",
        "BedroomsTotal", "BathroomsTotalInteger", "DaysOnMarket", "YearBuilt",
        "CloseDate", "ListingContractDate", "PurchaseContractDate", "CountyOrParish",
        "City", "PostalCode", "Latitude", "Longitude", "PropertyType",
        "PropertySubType", "ListingKey", "UnparsedAddress"]


def null_summary(df):
    s = pd.DataFrame({
        "null_count": df.isnull().sum(),
        "null_pct": (df.isnull().mean() * 100).round(2),
        "dtype": df.dtypes.astype(str),
    }).sort_values("null_pct", ascending=False)
    s["over_90pct"] = s["null_pct"] > 90
    s["core_field"] = s.index.isin(CORE)
    s["decision"] = np.where(s["over_90pct"] & ~s["core_field"], "DROP", "KEEP")
    return s


section("3. MISSING VALUE REPORT – SOLD")
ns = null_summary(sold)
print(ns.to_string())
ns.to_csv(EDA / "null_summary_sold.csv")
print(f"\nColumns >90% null ({ns.over_90pct.sum()}): {ns[ns.over_90pct].index.tolist()}")

section("3b. MISSING VALUE REPORT – LISTINGS")
nl = null_summary(listings)
print(nl.to_string())
nl.to_csv(EDA / "null_summary_listings.csv")
print(f"\nColumns >90% null ({nl.over_90pct.sum()}): {nl[nl.over_90pct].index.tolist()}")

print("\nDecision rule: drop columns >90% null UNLESS they are core market fields;"
      "\ncore fields are kept even if partially missing.")

# 4. NUMERIC DISTRIBUTIONS
NUMERIC = ["ClosePrice", "ListPrice", "OriginalListPrice", "LivingArea", "LotSizeAcres",
           "BedroomsTotal", "BathroomsTotalInteger", "DaysOnMarket", "YearBuilt"]
for c in NUMERIC:
    sold[c] = pd.to_numeric(sold[c], errors="coerce")

section("4. NUMERIC DISTRIBUTION SUMMARY – SOLD (Residential)")
PCTS = [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]
summ = sold[NUMERIC].describe(percentiles=PCTS).T
summ = summ.rename(columns={"50%": "median"})
# Extreme outliers: beyond 3x IQR from the quartiles (flag only – handled in a later week)
q1, q3 = sold[NUMERIC].quantile(0.25), sold[NUMERIC].quantile(0.75)
iqr = q3 - q1
lo, hi = q1 - 3 * iqr, q3 + 3 * iqr
summ["extreme_low_n"] = (sold[NUMERIC] < lo).sum()
summ["extreme_high_n"] = (sold[NUMERIC] > hi).sum()
summ["extreme_low_cut"], summ["extreme_high_cut"] = lo, hi
summ.to_csv(EDA / "numeric_summary_sold.csv")
print(summ.round(2).to_string())

print("\nKey fields (deliverable): ClosePrice, LivingArea, DaysOnMarket")
print(summ.loc[["ClosePrice", "LivingArea", "DaysOnMarket"],
               ["min", "1%", "5%", "25%", "median", "mean", "75%", "95%", "99%", "max"]]
      .round(1).to_string())

print("\nSuspicious values to handle in cleaning:")
print(f"  ClosePrice <= $1,000:         {(sold.ClosePrice <= 1000).sum():,}")
print(f"  ClosePrice >= $100M:          {(sold.ClosePrice >= 1e8).sum():,}  (likely data-entry errors)")
print(f"  LivingArea <= 100 sqft:       {(sold.LivingArea <= 100).sum():,}")
print(f"  DaysOnMarket < 0:             {(sold.DaysOnMarket < 0).sum():,}")
print(f"  YearBuilt < 1850 or > 2027:   {((sold.YearBuilt < 1850) | (sold.YearBuilt > 2027)).sum():,}")
print(f"  BedroomsTotal > 15:           {(sold.BedroomsTotal > 15).sum():,}")

# Histograms + boxplots (histogram clipped to 1st–99th pct so the shape is visible)
for c in NUMERIC:
    s = sold[c].dropna()
    if s.empty:
        continue
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4))
    p1, p99 = s.quantile([0.01, 0.99])
    a1.hist(s[(s >= p1) & (s <= p99)], bins=60, color="#4C72B0", edgecolor="white")
    a1.axvline(s.median(), color="#C44E52", ls="--", label=f"median {s.median():,.0f}")
    a1.set_title(f"{c} – histogram (1st–99th pct)"); a1.legend()
    # Heavily skewed fields get a log-scale boxplot (zeros can't be logged, so
    # they're excluded from the boxplot only – they're still counted above).
    if c in ("ClosePrice", "ListPrice", "OriginalListPrice", "LotSizeAcres", "LivingArea"):
        sb = s[s > 0]
        a2.boxplot(sb, orientation="horizontal", flierprops=dict(markersize=2, alpha=.3))
        a2.set_xscale("log")
        a2.set_title(f"{c} – boxplot, log scale (values > 0, n={len(sb):,})")
    else:
        a2.boxplot(s, orientation="horizontal", flierprops=dict(markersize=2, alpha=.3))
        a2.set_title(f"{c} – boxplot (all values, n={len(s):,})")
    fig.tight_layout(); fig.savefig(PLOTS / f"{c}.png", dpi=110); plt.close(fig)
print(f"\nPlots saved to {PLOTS.relative_to(BASE)}")

# 5. SUGGESTED QUESTIONS
section("5. EDA QUESTIONS")

print("Q1. Residential vs. other property type share (raw sold files):")
print(f"    Residential = {types.loc['Residential', 'Sold_%']:.1f}% of sold records, "
      f"{types.loc['Residential', 'Listing_%']:.1f}% of listing records")

print(f"\nQ2. Close price:  median ${sold.ClosePrice.median():,.0f}   "
      f"mean ${sold.ClosePrice.mean():,.0f}")
print("    (mean > median → right-skewed by luxury sales)")

d = sold.DaysOnMarket
print(f"\nQ3. Days on Market: median {d.median():.0f}, mean {d.mean():.1f}, "
      f"75th pct {d.quantile(.75):.0f}, 95th pct {d.quantile(.95):.0f}")
bins = pd.cut(d, [-np.inf, -1, 7, 14, 30, 60, 90, 180, np.inf],
              labels=["<0 (error)", "0-7", "8-14", "15-30", "31-60", "61-90", "91-180", "180+"])
print((bins.value_counts(normalize=True).sort_index() * 100).round(1).to_string())

valid = sold[(sold.ClosePrice > 0) & (sold.ListPrice > 0)]
ratio = valid.ClosePrice / valid.ListPrice
print(f"\nQ4. Sale price vs. list price (n={len(valid):,}):")
print(f"    Above list: {(ratio > 1).mean():.1%}   At list: {(ratio == 1).mean():.1%}   "
      f"Below list: {(ratio < 1).mean():.1%}")
print(f"    Median close-to-list ratio: {ratio.median():.3f}")

print("\nQ5. Date consistency checks:")
dates = {c: pd.to_datetime(sold[c], errors="coerce")
         for c in ("CloseDate", "ListingContractDate", "PurchaseContractDate")}
checks = {
    "CloseDate before ListingContractDate": dates["CloseDate"] < dates["ListingContractDate"],
    "CloseDate before PurchaseContractDate": dates["CloseDate"] < dates["PurchaseContractDate"],
    "PurchaseContractDate before ListingContractDate": dates["PurchaseContractDate"] < dates["ListingContractDate"],
    "CloseDate missing / unparseable": dates["CloseDate"].isna(),
    "CloseDate in the future": dates["CloseDate"] > pd.Timestamp.today(),
}
for k, m in checks.items():
    print(f"    {k:50s} {m.sum():>7,} ({m.mean():.2%})")
# Each sold file should only hold closings from its own month
file_month = sold["source_file"].str.extract(r"(\d{6})")[0]
close_month = dates["CloseDate"].dt.strftime("%Y%m")
mism = (file_month != close_month) & close_month.notna()
print(f"    {'CloseDate outside its monthly file':50s} {mism.sum():>7,} ({mism.mean():.2%})")

print("\nQ6. Counties with highest median close price (counties with ≥100 sales):")
cty = (sold.groupby("CountyOrParish")["ClosePrice"]
       .agg(sales="count", median_price="median", mean_price="mean")
       .query("sales >= 100").sort_values("median_price", ascending=False))
cty.to_csv(EDA / "county_median_price.csv")
print(cty.head(15).round(0).to_string())

# 6. SAVE FILTERED DATASETS (drop >90%-null non-core columns)
section("6. SAVE FILTERED DATASETS")
drop_s = ns[ns.decision == "DROP"].index.tolist()
drop_l = nl[nl.decision == "DROP"].index.tolist()
sold.drop(columns=drop_s).to_csv(OUT / "sold_residential_filtered.csv", index=False)
listings.drop(columns=drop_l).to_csv(OUT / "listings_residential_filtered.csv", index=False)
print(f"Sold:     dropped {drop_s} -> {sold.shape[1] - len(drop_s)} cols, {len(sold):,} rows")
print(f"Listings: dropped {drop_l} -> {listings.shape[1] - len(drop_l)} cols, {len(listings):,} rows")
print("Saved: output/sold_residential_filtered.csv")
print("Saved: output/listings_residential_filtered.csv")
