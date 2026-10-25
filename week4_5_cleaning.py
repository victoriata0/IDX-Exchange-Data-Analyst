"""
Weeks 4–5 – Data Cleaning and Preparation

Turns the enriched Residential datasets into clean, analysis-ready CSVs.
Every transformation is listed below with the reason for it, and the
script prints before/after row counts, dtype confirmations, date-consistency
flag counts, and a geographic data quality summary.

Inputs:  output/sold_with_rates.csv          (from week2_3_mortgage_rates.py)
         output/listings_with_rates.csv
Outputs: output/sold_cleaned.csv
         output/listings_cleaned.csv
         output/cleaning/cleaning_report.txt (everything printed below)

Transformations (in order)
  1. Convert date fields to datetime
       CloseDate, PurchaseContractDate, ListingContractDate,
       ContractStatusChangeDate – needed for date math and time series.
  2. Remove unnecessary / redundant columns
       MlsStatus, OriginatingSystemName  -> one value for every row (no info)
       ListAgentFirstName/LastName       -> duplicated by ListAgentFullName
       ListingKeyNumeric                 -> duplicate of ListingKey
       LotSizeArea                       -> mixed units; LotSizeAcres and
                                            LotSizeSquareFeet already cover it
       ListAgentEmail                    -> personal contact info, not needed
                                            for analysis
       latfilled/lonfilled               -> replaced by one boolean column,
                                            coords_backfilled_flag
  3. Handle missing values
       - Text: strip whitespace; empty strings become NaN
       - Y/N fields become True/False (missing stays missing)
       - Numeric fields are NOT filled in: imputing a price or size would
         invent data and bias medians. They stay NaN and Tableau/pandas
         skip them.
       - Sold rows missing CloseDate or ClosePrice are removed, because a
         sale with no date or price can't be analyzed.
  4. Make sure numeric fields are numeric (float, or nullable Int64 for counts)
  5. Remove invalid numeric values (business rules, always invalid)
       ClosePrice <= 0, ListPrice <= 0, LivingArea <= 0, DaysOnMarket < 0,
       BedroomsTotal < 0, BathroomsTotalInteger < 0
       (0 bedrooms is kept: studios are real.)
  6. Date consistency flags (rows are KEPT and flagged, not deleted)
       listing_after_close_flag  : ListingContractDate > CloseDate
       purchase_after_close_flag : PurchaseContractDate > CloseDate
       negative_timeline_flag    : PurchaseContractDate < ListingContractDate
  7. Geographic flags (rows are KEPT and flagged)
       missing_coords_flag       : Latitude or Longitude is null
       zero_coords_flag          : Latitude == 0 or Longitude == 0 (sentinel)
       positive_longitude_flag   : Longitude > 0 (California must be negative)
       out_of_state_coords_flag  : outside California's bounding box
       state_centroid_flag       : exactly the geographic center of California,
                                   which geocoders return when they can't find
                                   the address – a fake location
       invalid_coords_flag       : any of the above -> exclude from maps
     Finding: listing files for Jan–Aug 2024 are missing coordinates for
     20–80% of rows (the sold files for those months were geocoded by IDX –
     the *_filled.csv versions – but the listing files were not).
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent

# If this is a copy (e.g. github_upload/scripts), the data is one folder further up
if not any(BASE.glob("CRMLS*.csv")) and any(BASE.parent.glob("CRMLS*.csv")):
    BASE = BASE.parent
OUT = BASE / "output"
REPORT_DIR = OUT / "cleaning"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


class Tee:
    """Print to the console and to cleaning_report.txt at the same time."""
    def __init__(self, path):
        self.file = open(path, "w")
        self.stdout = sys.stdout
    def write(self, s):
        self.stdout.write(s); self.file.write(s)
    def flush(self):
        self.stdout.flush(); self.file.flush()

sys.stdout = Tee(REPORT_DIR / "cleaning_report.txt")
pd.set_option("display.width", 160, "display.max_rows", 200)

DATE_COLS = ["CloseDate", "PurchaseContractDate", "ListingContractDate",
             "ContractStatusChangeDate"]
DROP_COLS = ["MlsStatus", "OriginatingSystemName", "ListAgentFirstName",
             "ListAgentLastName", "ListingKeyNumeric", "LotSizeArea",
             "ListAgentEmail", "latfilled", "lonfilled"]
FLOAT_COLS = ["ClosePrice", "ListPrice", "OriginalListPrice", "LivingArea",
              "LotSizeAcres", "LotSizeSquareFeet", "AssociationFee",
              "Latitude", "Longitude", "rate_30yr_fixed", "BuyerAgencyCompensation"]
INT_COLS = ["BedroomsTotal", "BathroomsTotalInteger", "DaysOnMarket", "YearBuilt",
            "GarageSpaces", "ParkingTotal", "MainLevelBedrooms", "Stories",
            "StreetNumberNumeric"]
YN_COLS = ["ViewYN", "PoolPrivateYN", "AttachedGarageYN", "FireplaceYN",
           "NewConstructionYN"]

# California bounding box (generous by ~0.1°)
CA_LAT = (32.4, 42.1)
CA_LON = (-124.5, -114.0)
CA_CENTROID = (36.778261, -119.4179324)


def to_bool(s):
    """'True'/'False'/'Y'/'N'/1/0 -> nullable boolean; anything else -> <NA>."""
    m = {"true": True, "y": True, "yes": True, "1": True, "1.0": True,
         "false": False, "n": False, "no": False, "0": False, "0.0": False}
    return s.astype(str).str.strip().str.lower().map(m).astype("boolean")


def clean(df, name, is_sold):
    print(f"\n{name.upper()}")
    counts = [("Start (Residential, with mortgage rates)", len(df))]

    # 1. Dates 
    for c in DATE_COLS:
        if c in df:
            before_null = df[c].isna().sum()
            df[c] = pd.to_datetime(df[c], errors="coerce")
            bad = df[c].isna().sum() - before_null
            print(f"1. {c:26s} -> datetime  (unparseable values set to NaT: {bad})")

    # 2. Drop unnecessary columns 
    if "latfilled" in df:
        df["coords_backfilled_flag"] = to_bool(df["latfilled"]).fillna(False).astype(bool)
    dropped = [c for c in DROP_COLS if c in df]
    df = df.drop(columns=dropped)
    print(f"\n2. Dropped {len(dropped)} redundant columns: {dropped}")

    # 3. Missing values 
    # ("string" covers pandas 3, where text columns get the new str dtype)
    obj = df.select_dtypes(include=["object", "string"]).columns
    blanks = 0
    for c in obj:
        # Some text columns mix strings with True/False, so only strip strings
        df[c] = df[c].map(lambda v: v.strip() if isinstance(v, str) else v)
        blanks += (df[c] == "").sum()
        df[c] = df[c].replace("", np.nan)
    print(f"\n3. Stripped whitespace in {len(obj)} text columns; "
          f"{blanks:,} empty strings -> NaN")
    for c in YN_COLS:
        if c in df:
            df[c] = to_bool(df[c])
    print(f"   Converted Y/N fields to boolean: {[c for c in YN_COLS if c in df]}")
    if is_sold:
        n = len(df)
        df = df.dropna(subset=["CloseDate", "ClosePrice"])
        counts.append(("Removed: missing CloseDate or ClosePrice", n - len(df)))

    # 4. Numeric types 
    for c in FLOAT_COLS:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    for c in INT_COLS:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce").round().astype("Int64")

    # 5. Invalid numeric values 
    rules = {
        "ClosePrice <= 0": df["ClosePrice"] <= 0,
        "ListPrice <= 0": df["ListPrice"] <= 0,
        "LivingArea <= 0": df["LivingArea"] <= 0,
        "DaysOnMarket < 0": df["DaysOnMarket"] < 0,
        "BedroomsTotal < 0": df["BedroomsTotal"] < 0,
        "BathroomsTotalInteger < 0": df["BathroomsTotalInteger"] < 0,
    }
    print("\n5. Invalid numeric values (removed):")
    invalid = pd.Series(False, index=df.index)
    for k, m in rules.items():
        m = m.fillna(False).astype(bool)
        print(f"   {k:28s} {m.sum():>7,}")
        invalid |= m
    n = len(df)
    df = df[~invalid].copy()
    counts.append(("Removed: invalid numeric values (any rule)", n - len(df)))

    # 6. Date consistency flags 
    df["listing_after_close_flag"] = (df["ListingContractDate"] > df["CloseDate"]).fillna(False).astype(bool)
    df["purchase_after_close_flag"] = (df["PurchaseContractDate"] > df["CloseDate"]).fillna(False).astype(bool)
    df["negative_timeline_flag"] = (df["PurchaseContractDate"] < df["ListingContractDate"]).fillna(False).astype(bool)
    print("\n6. Date consistency flags (rows kept):")
    for c in ["listing_after_close_flag", "purchase_after_close_flag", "negative_timeline_flag"]:
        print(f"   {c:28s} {df[c].sum():>7,}  ({df[c].mean():.2%})")

    # 7. Geographic flags 
    lat, lon = df["Latitude"], df["Longitude"]
    df["missing_coords_flag"] = lat.isna() | lon.isna()
    df["zero_coords_flag"] = (lat == 0) | (lon == 0)
    df["positive_longitude_flag"] = lon > 0
    has = ~df["missing_coords_flag"] & ~df["zero_coords_flag"]
    df["out_of_state_coords_flag"] = has & ~(lat.between(*CA_LAT) & lon.between(*CA_LON))
    df["state_centroid_flag"] = (lat.round(4) == round(CA_CENTROID[0], 4)) & \
                                (lon.round(4) == round(CA_CENTROID[1], 4))
    geo = ["missing_coords_flag", "zero_coords_flag", "positive_longitude_flag",
           "out_of_state_coords_flag", "state_centroid_flag"]
    df["invalid_coords_flag"] = df[geo].any(axis=1)
    print("\n7. Geographic data quality (rows kept, flagged):")
    for c in geo + ["invalid_coords_flag"]:
        print(f"   {c:28s} {df[c].sum():>7,}  ({df[c].mean():.2%})")
    if "coords_backfilled_flag" in df:
        print(f"   {'coords_backfilled_flag':28s} {df['coords_backfilled_flag'].sum():>7,}"
              "  (lat/lon geocoded by IDX – informational)")
    print(f"   Records with usable coordinates for maps: {(~df['invalid_coords_flag']).sum():,}")
    # Missing coordinates are not spread evenly – show any month above 5%
    by_month = df.groupby("source_file")["missing_coords_flag"].mean() * 100
    bad_months = by_month[by_month > 5]
    if len(bad_months):
        print("   Months with >5% missing coordinates (source-data gap):")
        for f, pct in bad_months.items():
            print(f"     {f:32s} {pct:5.1f}%")
        print("   -> For maps, aggregate by PostalCode (present on 99.99% of rows) instead of "
              "plotting points.")

    # Summary 
    counts.append(("Final cleaned rows", len(df)))
    print("\nROW COUNTS")
    for k, v in counts:
        print(f"   {k:45s} {v:>9,}")
    print(f"   Columns: {df.shape[1]}")

    print("\nDATA TYPE CONFIRMATION (key fields)")
    key = DATE_COLS + ["ClosePrice", "ListPrice", "OriginalListPrice", "LivingArea",
                       "BedroomsTotal", "BathroomsTotalInteger", "DaysOnMarket",
                       "YearBuilt", "Latitude", "Longitude", "rate_30yr_fixed"] + YN_COLS
    print(df[[c for c in key if c in df]].dtypes.to_string())
    return df


sold = pd.read_csv(OUT / "sold_with_rates.csv", low_memory=False)
sold = clean(sold, "sold", is_sold=True)
sold.to_csv(OUT / "sold_cleaned.csv", index=False)
print("\nSaved: output/sold_cleaned.csv")
del sold

listings = pd.read_csv(OUT / "listings_with_rates.csv", low_memory=False)
listings = clean(listings, "listings", is_sold=False)
listings.to_csv(OUT / "listings_cleaned.csv", index=False)
print("\nSaved: output/listings_cleaned.csv")
