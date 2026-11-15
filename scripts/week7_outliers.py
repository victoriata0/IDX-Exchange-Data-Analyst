"""
Week 7 – Outlier Detection and Data Quality
-------------------------------------------
Flags extreme values with the Interquartile Range (IQR) method and builds a
separate filtered analysis dataset, without deleting anything from the full
dataset.

Input:   output/sold_features.csv  (from week6_features.py), or, if Week 6
         hasn't been run yet, output/sold_cleaned.csv (Weeks 4–5) with
         price_per_sqft and close_to_original_list_ratio computed here
Outputs: output/sold_flagged.csv     every row + outlier flag columns
         output/sold_filtered.csv    clean analysis dataset
         output/week7/outlier_report.txt  everything printed below,
                                          including the written comparison

Tiered approach (as the handbook recommends: flag first, don't blindly delete)
  Tier 1 – business rules: values that are always invalid (ClosePrice <= 0,
           LivingArea <= 0, DaysOnMarket < 0). Already removed in Weeks 4–5;
           re-checked here.
           New rule: a price ratio below 0.5 or above 2 means the list price
           was entered wrong (e.g. OriginalListPrice = $1 gives a ratio of
           millions). The sale itself is fine, so the row is kept, flagged with
           ratio_entry_error_flag, and the bad ratio is blanked in the
           filtered dataset.
  Tier 2 – IQR flags. For each field:
               Q1, Q3 = 25th and 75th percentiles, IQR = Q3 - Q1
               lower = Q1 - 1.5 * IQR,  upper = Q3 + 1.5 * IQR
           A row outside [lower, upper] gets <field>_outlier_flag = True.
           Fields: ClosePrice, LivingArea, DaysOnMarket (the key fields),
           plus price_per_sqft and close_to_original_list_ratio.
  Tier 3 – filtered dataset. Leaves out rows flagged on the three key fields
           (ClosePrice, LivingArea, DaysOnMarket) and older duplicate copies
           of a listing (from Weeks 4–5).
           price_per_sqft and close_to_original_list_ratio are flagged only:
           at 1.5 * IQR the ratio flag catches normal homes that had a 15%+
           price cut, which is real market behavior, not bad data.

Percentiles (1st / 99th) are printed next to every IQR bound to show how much
of the data each bound cuts.
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
REPORT_DIR = OUT / "week7"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


class Tee:
    """Print to the console and to outlier_report.txt at the same time."""
    def __init__(self, path):
        # buffering=1 writes each line right away, so the report is complete
        # even when IDLE keeps the program running after it finishes
        self.file = open(path, "w", buffering=1)
        self.stdout = sys.stdout
    def write(self, s):
        self.stdout.write(s); self.file.write(s)
    def flush(self):
        self.stdout.flush(); self.file.flush()

sys.stdout = Tee(REPORT_DIR / "outlier_report.txt")
pd.set_option("display.width", 200, "display.max_columns", 20)

KEY_FIELDS = ["ClosePrice", "LivingArea", "DaysOnMarket"]          # flag + filter
FLAG_ONLY = ["price_per_sqft", "close_to_original_list_ratio"]     # flag only
ALL_FIELDS = KEY_FIELDS + FLAG_ONLY

# Load
features = OUT / "sold_features.csv"
if features.exists():
    df = pd.read_csv(features, low_memory=False)
    print("Input: output/sold_features.csv (Week 6)")
else:
    df = pd.read_csv(OUT / "sold_cleaned.csv", low_memory=False)
    df["price_per_sqft"] = df["ClosePrice"] / df["LivingArea"].where(df["LivingArea"] > 0)
    df["close_to_original_list_ratio"] = (df["ClosePrice"] /
                                          df["OriginalListPrice"].where(df["OriginalListPrice"] > 0))
    print("Input: output/sold_cleaned.csv (Weeks 4–5) – Week 6 not run yet, so\n"
          "       price_per_sqft and close_to_original_list_ratio were computed here")
start_rows, start_cols = df.shape
print(f"Rows: {start_rows:,}   Columns: {start_cols}")

# Tier 1 – business rules
print("\nTIER 1 – BUSINESS RULES (always invalid)")
rules = {"ClosePrice <= 0": df["ClosePrice"] <= 0,
         "LivingArea <= 0": df["LivingArea"] <= 0,
         "DaysOnMarket < 0": df["DaysOnMarket"] < 0}
for k, m in rules.items():
    print(f"   {k:20s} {int(m.sum()):>6,}")
print("   (all 0 – these were removed in Weeks 4–5)")

RATIOS = [c for c in ("price_ratio", "close_to_original_list_ratio") if c in df]
bad_ratio = pd.Series(False, index=df.index)
for c in RATIOS:
    m = (df[c] < 0.5) | (df[c] > 2)
    print(f"   {c} < 0.5 or > 2 (list price entry error): {int(m.sum()):,}")
    bad_ratio |= m
df["ratio_entry_error_flag"] = bad_ratio
print(f"   ratio_entry_error_flag: {int(bad_ratio.sum()):,} rows "
      "(kept; ratio blanked in the filtered dataset)")

# Tier 2 – IQR flags
print("\nTIER 2 – IQR OUTLIER FLAGS (lower = Q1 - 1.5*IQR, upper = Q3 + 1.5*IQR)")
rows = []
for c in ALL_FIELDS:
    s = df[c]
    if c in RATIOS:
        s = s.mask(df["ratio_entry_error_flag"])   # entry errors don't shape the bounds
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    low, high = s < lower, s > upper
    df[f"{c}_outlier_flag"] = (low | high).fillna(False).astype(bool)
    rows.append({"field": c, "Q1": q1, "Q3": q3, "IQR": iqr,
                 "lower": lower, "upper": upper,
                 "p1": s.quantile(0.01), "p99": s.quantile(0.99),
                 "below_lower": int(low.sum()), "above_upper": int(high.sum()),
                 "flagged_pct": df[f"{c}_outlier_flag"].mean() * 100,
                 "use": "flag + filter" if c in KEY_FIELDS else "flag only"})
bounds = pd.DataFrame(rows).set_index("field")
bounds.to_csv(REPORT_DIR / "iqr_bounds.csv")
show = bounds.copy()
for c in ["Q1", "Q3", "IQR", "lower", "upper", "p1", "p99"]:
    show[c] = show[c].map(lambda v: f"{v:,.2f}")
show["flagged_pct"] = show["flagged_pct"].map(lambda v: f"{v:.1f}%")
print(show.to_string())
print("\nNote: for prices, sizes and days on market the lower bound is negative,\n"
      "so IQR only flags the high end. Those fields can't go below 0.")

df["key_outlier_flag"] = df[[f"{c}_outlier_flag" for c in KEY_FIELDS]].any(axis=1)
df["any_outlier_flag"] = df[[f"{c}_outlier_flag" for c in ALL_FIELDS]].any(axis=1)
print(f"\n   key_outlier_flag (any of {', '.join(KEY_FIELDS)}): "
      f"{df['key_outlier_flag'].sum():,} ({df['key_outlier_flag'].mean():.1%})")
print(f"   any_outlier_flag (any of all 5 fields):                  "
      f"{df['any_outlier_flag'].sum():,} ({df['any_outlier_flag'].mean():.1%})")

print("\n   Where the ClosePrice outliers are (top 5 counties):")
top = df.loc[df["ClosePrice_outlier_flag"], "CountyOrParish"].value_counts().head(5)
for county, n in top.items():
    print(f"     {county:20s} {n:>6,}")

# Tier 3 – filtered dataset
print("\nTIER 3 – FILTERED ANALYSIS DATASET")
steps = [("Full flagged dataset", len(df))]
filtered = df[~df["key_outlier_flag"]]
steps.append(("Removed: outlier on ClosePrice, LivingArea or DaysOnMarket", len(df) - len(filtered)))
if "duplicate_listingkey_flag" in filtered:
    n = len(filtered)
    filtered = filtered[~filtered["duplicate_listingkey_flag"].astype(bool)]
    steps.append(("Removed: older duplicate copy of a listing (Weeks 4–5 flag)", n - len(filtered)))
filtered = filtered.copy()
for c in RATIOS:
    filtered.loc[filtered["ratio_entry_error_flag"], c] = np.nan
steps.append(("Filtered dataset", len(filtered)))
for k, v in steps:
    print(f"   {k:62s} {v:>9,}")

# Written comparison
print("\nBEFORE vs AFTER FILTERING")
cmp_fields = KEY_FIELDS + FLAG_ONLY + (["price_ratio"] if "price_ratio" in df else [])
comp = pd.DataFrame({
    "median_before": df[cmp_fields].median(),
    "median_after": filtered[cmp_fields].median(),
    "mean_before": df[cmp_fields].mean(),
    "mean_after": filtered[cmp_fields].mean(),
})
comp["median_change_pct"] = (comp["median_after"] / comp["median_before"] - 1) * 100
comp.to_csv(REPORT_DIR / "before_after_comparison.csv")
print(comp.round(3).to_string())

mb, ma = df["ClosePrice"].median(), filtered["ClosePrice"].median()
eb, ea = df["ClosePrice"].mean(), filtered["ClosePrice"].mean()
db, da = df["DaysOnMarket"].median(), filtered["DaysOnMarket"].median()
lb, la = df["LivingArea"].median(), filtered["LivingArea"].median()
removed = len(df) - len(filtered)
print(f"""
Written comparison
   Size: the filtered dataset keeps {len(filtered):,} of {len(df):,} sales
   ({len(filtered) / len(df):.1%}); {removed:,} rows ({removed / len(df):.1%}) are left out.
   The full dataset is saved too, with every flag, so nothing is lost.

   Prices: the median close price moves from ${mb:,.0f} to ${ma:,.0f}
   ({(ma / mb - 1) * 100:+.1f}%), while the mean drops from ${eb:,.0f} to ${ea:,.0f}
   ({(ea / eb - 1) * 100:+.1f}%). The mean moves much more than the median
   because a few very expensive sales (up to ${df['ClosePrice'].max():,.0f}) pull the
   mean up. That is why the dashboards should report medians.

   Size and speed: median living area {lb:,.0f} -> {la:,.0f} sq ft, median days
   on market {db:.0f} -> {da:.0f}.

   Caveat: the IQR bounds are statewide. The ClosePrice upper bound
   (${bounds.loc['ClosePrice', 'upper']:,.0f}) flags many ordinary homes in high-cost counties
   (Los Angeles, Orange, Santa Clara, San Mateo), so for county-level
   analysis of expensive areas, use the full flagged dataset or compute
   IQR bounds per county.
""")

# Save
df.to_csv(OUT / "sold_flagged.csv", index=False)
filtered.to_csv(OUT / "sold_filtered.csv", index=False)
print(f"Saved: output/sold_flagged.csv  ({len(df):,} rows x {df.shape[1]} columns, "
      f"{df.shape[1] - start_cols} flag columns added)")
print(f"Saved: output/sold_filtered.csv ({len(filtered):,} rows)")
