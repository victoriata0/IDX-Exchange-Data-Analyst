"""
Week 6 – Feature Engineering and Market 
Adds the market metrics that power the Tableau dashboards, assigns each
home to its school district(s) from latitude/longitude, and produces
segment summary tables.

Input:   output/sold_cleaned.csv                  (from week4_5_cleaning.py)
Outputs: output/sold_features.csv                 sold data + all new columns
         output/week6/feature_report.txt          everything printed below
         output/week6/segment_*.csv               segment summary tables
         data_external/school_districts_2024_25.geojson   (downloaded once)

New columns
  price_ratio                  ClosePrice / ListPrice
                               Sale price vs. final asking price –
                               negotiation strength.
  close_to_original_list_ratio ClosePrice / OriginalListPrice
                               Sale price vs. first asking price – captures
                               every price cut along the way.
                               (The handbook lists the same formula for both
                               ratios; using ListPrice for the first one makes
                               them measure two different things.)
  price_per_sqft               ClosePrice / LivingArea
                               Normalizes price across home sizes.
  DaysOnMarket                 Raw MLS field, kept as is (time to sell).
  close_year, close_month,     From CloseDate, for time-series charts.
  close_yrmo                   close_yrmo looks like '2024-01'.
  listing_to_contract_days     PurchaseContractDate - ListingContractDate
                               Time from listing to accepted offer.
  contract_to_close_days       CloseDate - PurchaseContractDate
                               Escrow / closing period.
  school_district_unified,     School district(s) the home falls inside.
  school_district_elementary,  California has unified districts (K-12) and
  school_district_high         separate elementary + high school districts
                               that overlap, so a home gets either a unified
                               district or an elementary and a high district.
  school_district              One label per home: unified if there is one,
                               otherwise the elementary district.

Ratios use only valid denominators (> 0). Homes with invalid coordinates
(invalid_coords_flag from Weeks 4–5) get no school district.

Segment tables use one row per listing (older duplicate copies, flagged in
Weeks 4–5, are left out) and medians, which outliers don't distort.
Extreme values are handled in Week 7.
"""
from pathlib import Path
import io
import json
import sys

import numpy as np
import pandas as pd
import requests
from matplotlib.path import Path as MplPath

BASE = Path(__file__).resolve().parent.parent

# If this is a copy (e.g. github_upload/scripts), the data is one folder further up
if not any(BASE.glob("CRMLS*.csv")) and any(BASE.parent.glob("CRMLS*.csv")):
    BASE = BASE.parent
OUT = BASE / "output"
REPORT_DIR = OUT / "week6"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
EXT = BASE / "data_external"
EXT.mkdir(exist_ok=True)

# California School District Areas 2024-25 (California Department of Education)
# https://data.ca.gov/dataset/california-school-district-areas-2024-25
DISTRICTS_URL = ("https://gis.data.ca.gov/api/download/v1/items/"
                 "b0e3b936426a47ce9d9a2e77e2bb86cc/geojson?layers=0")
DISTRICTS_FILE = EXT / "school_districts_2024_25.geojson"


class Tee:
    """Print to the console and to feature_report.txt at the same time."""
    def __init__(self, path):
        self.file = open(path, "w")
        self.stdout = sys.stdout
    def write(self, s):
        self.stdout.write(s); self.file.write(s)
    def flush(self):
        self.stdout.flush(); self.file.flush()

sys.stdout = Tee(REPORT_DIR / "feature_report.txt")
pd.set_option("display.width", 200, "display.max_columns", 30, "display.max_rows", 100)


def safe_divide(a, b):
    """a / b, but NaN wherever b is missing or not positive."""
    return a / b.where(b > 0)


# Load
DATES = ["CloseDate", "PurchaseContractDate", "ListingContractDate"]
sold = pd.read_csv(OUT / "sold_cleaned.csv", low_memory=False, parse_dates=DATES)
start_cols = sold.shape[1]
print(f"Loaded sold_cleaned.csv: {len(sold):,} rows x {start_cols} columns")

# 1. Market metrics
print("\n1. MARKET METRICS")
sold["price_ratio"] = safe_divide(sold["ClosePrice"], sold["ListPrice"])
sold["close_to_original_list_ratio"] = safe_divide(sold["ClosePrice"], sold["OriginalListPrice"])
sold["price_per_sqft"] = safe_divide(sold["ClosePrice"], sold["LivingArea"])

sold["close_year"] = sold["CloseDate"].dt.year
sold["close_month"] = sold["CloseDate"].dt.month
sold["close_yrmo"] = sold["CloseDate"].dt.strftime("%Y-%m")

sold["listing_to_contract_days"] = (sold["PurchaseContractDate"] - sold["ListingContractDate"]).dt.days
sold["contract_to_close_days"] = (sold["CloseDate"] - sold["PurchaseContractDate"]).dt.days

METRICS = ["price_ratio", "close_to_original_list_ratio", "price_per_sqft", "DaysOnMarket",
           "listing_to_contract_days", "contract_to_close_days"]
summary = sold[METRICS].describe(percentiles=[0.05, 0.25, 0.5, 0.75, 0.95]).T
summary.insert(1, "missing", sold[METRICS].isna().sum())
print(summary.round(3).to_string())

print("\nChecks:")
print(f"   close_year range: {sold['close_year'].min()}–{sold['close_year'].max()}, "
      f"{sold['close_yrmo'].nunique()} distinct months")
neg_ltc = (sold["listing_to_contract_days"] < 0).sum()
neg_ctc = (sold["contract_to_close_days"] < 0).sum()
print(f"   listing_to_contract_days < 0: {neg_ltc:,} "
      f"(= negative_timeline_flag rows from Weeks 4–5)")
print(f"   contract_to_close_days < 0:   {neg_ctc:,} "
      f"(= purchase_after_close_flag rows from Weeks 4–
      
# 2. School districts (point-in-polygon on latitude/longitude)
print("\n2. SCHOOL DISTRICTS")
if not DISTRICTS_FILE.exists():
    print("   Downloading California School District Areas 2024-25 ...")
    r = requests.get(DISTRICTS_URL, timeout=300)
    r.raise_for_status()
    DISTRICTS_FILE.write_bytes(r.content)
gj = json.loads(DISTRICTS_FILE.read_text())
features = gj["features"]
props = pd.DataFrame([f["properties"] for f in features])
print(f"   {len(features):,} district boundaries loaded")
print(f"   Fields in the file: {list(props.columns)}")

# Find the name and type columns without hard-coding their exact spelling
name_col = next((c for c in props.columns if c.lower() in ("districtname", "district_name", "district", "name")),
                next(c for c in props.columns if "name" in c.lower()))
type_col = next(c for c in props.columns if "type" in c.lower())
print(f"   Using name field '{name_col}' and type field '{type_col}'")
print(f"   District types: {props[type_col].value_counts().to_dict()}")


def type_bucket(t):
    t = str(t).lower()
    if "unified" in t:
        return "unified"
    if "high" in t or "secondary" in t:
        return "high"
    if "elem" in t:
        return "elementary"
    return None


def rings(geometry):
    """Yield (outer ring, [holes]) for Polygon and MultiPolygon geometry."""
    if geometry is None:
        return
    if geometry["type"] == "Polygon":
        polys = [geometry["coordinates"]]
    elif geometry["type"] == "MultiPolygon":
        polys = geometry["coordinates"]
    else:
        return
    for poly in polys:
        yield np.asarray(poly[0])[:, :2], [np.asarray(h)[:, :2] for h in poly[1:]]


ok = ~sold["invalid_coords_flag"].astype(bool) & sold["Latitude"].notna() & sold["Longitude"].notna()
pts = sold.loc[ok, ["Longitude", "Latitude"]].to_numpy()   # GeoJSON order is lon, lat
idx = sold.index[ok]
assigned = {b: pd.Series(pd.NA, index=sold.index, dtype="string")
            for b in ("unified", "elementary", "high")}

for feat, (_, row) in zip(features, props.iterrows()):
    bucket = type_bucket(row[type_col])
    if bucket is None:
        continue
    inside = np.zeros(len(pts), dtype=bool)
    for outer, holes in rings(feat.get("geometry")):
        # Quick bounding-box filter, then exact point-in-polygon test
        lo, hi = outer.min(axis=0), outer.max(axis=0)
        cand = np.where((pts[:, 0] >= lo[0]) & (pts[:, 0] <= hi[0]) &
                        (pts[:, 1] >= lo[1]) & (pts[:, 1] <= hi[1]))[0]
        if len(cand) == 0:
            continue
        hit = MplPath(outer).contains_points(pts[cand])
        for h in holes:
            hit &= ~MplPath(h).contains_points(pts[cand])
        inside[cand[hit]] = True
    if inside.any():
        target = assigned[bucket]
        empty = target.loc[idx[inside]].isna()
        target.loc[idx[inside][empty.to_numpy()]] = str(row[name_col])

for b, s in assigned.items():
    sold[f"school_district_{b}"] = s
sold["school_district"] = sold["school_district_unified"].fillna(sold["school_district_elementary"])

matched = sold["school_district"].notna()
print(f"\n   Homes with usable coordinates: {ok.sum():,}")
print(f"   Matched to a school district:  {matched.sum():,} ({matched.sum() / ok.sum():.1%} of those)")
print(f"     in a unified district:       {sold['school_district_unified'].notna().sum():,}")
print(f"     in an elementary district:   {sold['school_district_elementary'].notna().sum():,}")
print(f"     in a high school district:   {sold['school_district_high'].notna().sum():,}")
print(f"   No district (bad/missing coordinates or outside all boundaries): {(~matched).sum():,}")

# 3. Sample output – new columns populated
print("\n3. SAMPLE OUTPUT (new columns)")
SAMPLE_COLS = ["CloseDate", "ClosePrice", "ListPrice", "OriginalListPrice", "LivingArea",
               "price_ratio", "close_to_original_list_ratio", "price_per_sqft", "DaysOnMarket",
               "close_yrmo", "listing_to_contract_days", "contract_to_close_days", "school_district"]
sample = sold.loc[matched].sample(8, random_state=42)[SAMPLE_COLS].copy()
sample["CloseDate"] = sample["CloseDate"].dt.strftime("%Y-%m-%d")
for c in ["ClosePrice", "ListPrice", "OriginalListPrice", "LivingArea", "price_per_sqft"]:
    sample[c] = sample[c].round(0)
for c in ["price_ratio", "close_to_original_list_ratio"]:
    sample[c] = sample[c].round(3)
print(sample.to_string(index=False))

# 4. Segment analysis
base = sold
if "duplicate_listingkey_flag" in sold:
    base = sold[~sold["duplicate_listingkey_flag"].astype(bool)]


def segment(df, by, min_sales=1):
    g = df.groupby(by, dropna=True)
    t = pd.DataFrame({
        "sales": g.size(),
        "median_close_price": g["ClosePrice"].median(),
        "median_price_per_sqft": g["price_per_sqft"].median(),
        "median_days_on_market": g["DaysOnMarket"].median(),
        "median_price_ratio": g["price_ratio"].median(),
        "median_close_to_original": g["close_to_original_list_ratio"].median(),
        "median_contract_to_close_days": g["contract_to_close_days"].median(),
    })
    return t[t["sales"] >= min_sales].sort_values("sales", ascending=False)


def save(t, name, title, rows=15):
    t.to_csv(REPORT_DIR / f"segment_{name}.csv")
    print(f"\n{title}  ({len(t):,} groups, top {min(rows, len(t))} shown, "
          f"full table: output/week6/segment_{name}.csv)")
    print(t.head(rows).round(3).to_string())


print("\n4. SEGMENT ANALYSIS (one row per listing, medians)")
save(segment(base, ["PropertyType", "PropertySubType"]), "property_type",
     "By PropertyType / PropertySubType")
save(segment(base, "CountyOrParish", min_sales=100), "county",
     "By county (counties with 100+ sales)", rows=20)
save(segment(base, ["CountyOrParish", "MLSAreaMajor"], min_sales=100), "county_mls_area",
     "By county / MLS area (areas with 100+ sales)")
save(segment(base, "school_district", min_sales=100).sort_values("median_close_price", ascending=False),
     "school_district", "By school district – highest median price (districts with 100+ sales)")


def office_table(col):
    g = base.groupby(col, dropna=True)
    t = pd.DataFrame({"units": g.size(),
                      "sales_volume": g["ClosePrice"].sum(),
                      "median_close_price": g["ClosePrice"].median(),
                      "median_days_on_market": g["DaysOnMarket"].median()})
    return t.sort_values("sales_volume", ascending=False)


for col, name in (("ListOfficeName", "list_office"), ("BuyerOfficeName", "buyer_office")):
    t = office_table(col)
    t.to_csv(REPORT_DIR / f"segment_{name}.csv")
    print(f"\nTop 10 by sales volume – {col}  (full table: output/week6/segment_{name}.csv)")
    show = t.head(10).copy()
    show["sales_volume"] = (show["sales_volume"] / 1e6).round(1).astype(str) + "M"
    show["median_close_price"] = show["median_close_price"].round(0)
    print(show.to_string())

# 5. Save
sold.to_csv(OUT / "sold_features.csv", index=False)
print(f"\n5. SAVED output/sold_features.csv: {len(sold):,} rows x {sold.shape[1]} columns "
      f"({sold.shape[1] - start_cols} new)")
