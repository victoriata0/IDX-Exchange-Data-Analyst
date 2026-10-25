# IDX Exchange Internship – MLS Data Pipeline

Python pipeline that turns monthly California MLS (CRMLS) exports into clean,
analysis-ready datasets for market analytics and Tableau dashboards.

**Data:** 56 monthly CSV files, January 2024 – April 2026
(28 listing files + 28 sold files) from the CoreLogic Trestle API via IDX Exchange.
The raw data is confidential MLS data and is **not** included in this repo.


## Row counts at a glance

| Stage | Sold rows | Listing rows | Script |
|---|---:|---:|---|
| Raw monthly files combined (all property types) | 615,707 | 872,785 | Week 1 |
| After `PropertyType == 'Residential'` filter | 414,054 | 557,051 | Week 1 |
| After dropping >90%-empty columns | 414,054 | 557,051 | Weeks 2–3 EDA |
| After merging mortgage rates | 414,054 | 557,051 | Weeks 2–3 rates |
| **After cleaning (final analysis-ready data)** | **413,853** | **556,656** | Weeks 4–5 |

| Stage | Sold columns | Listing columns |
|---|---:|---:|
| Week 1 combined | 85 | 74 |
| Weeks 2–3 after dropping empty columns | 70 | 59 |
| Weeks 2–3 after adding mortgage rate | 72 | 61 |
| Weeks 4–5 cleaned (redundant columns out, flag columns in) | 73 | 64 |



## Week 0 – Data Pipeline Orientation

Monthly files were downloaded from the IDX Exchange FTP. Three listing files
(Jan 2024, Mar 2024, Jan 2026) were **cut off mid-download** – e.g. March 2024
had 8,030 rows instead of ~25,000 – so they were re-extracted from the Trestle
API. Because the API returns records added after the FTP files were generated,
listing counts can be slightly higher than other interns' (sold counts match).



## Week 1 – Monthly Dataset Aggregation

**Script:** `scripts/week1_combine.py`

**What it does**
- Loads every `CRMLSListingYYYYMM.csv` and `CRMLSSoldYYYYMM.csv` from Jan 2024
  to the latest month in the folder and stacks them with `pd.concat`
- Uses the `*_filled.csv` version of a sold month when one exists
  (those have back-filled latitude/longitude)
- Drops 11 duplicate columns in the listing files (e.g. `ListPrice.1`), caused
  by the extraction script requesting those fields twice
- Warns if a file looks truncated (doesn't end with a newline)
- Filters both datasets to `PropertyType == 'Residential'`

**Row counts**

| | Before concat | After concat | After Residential filter | % kept |
|---|---|---:|---:|---:|
| Sold | 28 files, 16,487–26,487 rows each | 615,707 | 414,054 | 67.2% |
| Listings | 28 files, 18,773–40,271 rows each | 872,785 | 557,051 | 63.8% |

**Output:** `output/combined_sold_residential.csv`, `output/combined_listings_residential.csv`



## Weeks 2–3 – Dataset Structuring, Validation & EDA

**Script:** `scripts/week2_3_eda.py` · **Full output:** `results/eda_report.txt`

**What it does and what the outputs show**

1. **Property types** – counts every `PropertyType` in the raw files
   (`results/property_type_counts.csv`). Residential is 67.2% of sold records
   and 63.8% of listings. The rest is mostly ResidentialLease (rentals, 22.9%),
   Land, and ManufacturedInPark, which are excluded because they price differently.
2. **Structure** – rows, columns, and data type of every column.
3. **Missing values** – null count and % for every column
   (`results/null_summary_sold.csv`, `results/null_summary_listings.csv`).
   **15 columns are >90% empty in each dataset** and are dropped
   (e.g. TaxAnnualAmount, BuilderName, AboveGradeFinishedArea).
   Core fields like price, size, and dates are kept even if partially missing.
4. **Numeric distributions** – min, max, mean, median, and percentiles for
   ClosePrice, ListPrice, OriginalListPrice, LivingArea, LotSizeAcres,
   BedroomsTotal, BathroomsTotalInteger, DaysOnMarket, YearBuilt
   (`results/numeric_summary_sold.csv`), plus a histogram and boxplot for each
   (`results/plots/`). Extreme outliers flagged for later: 40 sales ≥ $100M
   (data-entry errors, max $990M), 207 homes ≤ 100 sq ft, 48 negative DOM.

**EDA questions answered**

| Question | Answer |
|---|---|
| Residential share | 67.2% of sold, 63.8% of listings |
| Median / average close price | $823,000 / $1,193,864 (right-skewed by luxury sales) |
| Days on market | Median 18, mean 37.4; 63% sell within 30 days |
| Sold above / at / below list | 40.1% / 17.4% / 42.5% |
| Date problems | 61 closed before listing (0.01%), 239 closed before contract |
| Highest median price counties | San Mateo $1.70M, Santa Clara $1.60M, Santa Cruz $1.20M (`results/county_median_price.csv`) |

**Row counts:** unchanged (414,054 sold, 557,051 listings) – this step removes
columns, not rows. Sold 85 → 70 columns, listings 74 → 59.

**Output:** `output/sold_residential_filtered.csv`, `output/listings_residential_filtered.csv`



## Weeks 2–3 – Mortgage Rate Enrichment

**Script:** `scripts/week2_3_mortgage_rates.py`

**What it does**
1. Downloads the FRED `MORTGAGE30US` series (30-year fixed rate, weekly)
2. Averages it to one rate per month (`results/mortgage30us_monthly.csv`)
3. Adds a `year_month` key – from `CloseDate` for sold, `ListingContractDate` for listings
4. Left-joins the monthly rate onto both datasets
5. Validates: row counts unchanged and **0 null rates** in either dataset

**Row counts:** unchanged – 414,054 sold, 557,051 listings (+2 columns:
`year_month`, `rate_30yr_fixed`). Rates in the data range from 6.05%
(Feb 2026) to 7.06% (May 2024).

**Output:** `output/sold_with_rates.csv`, `output/listings_with_rates.csv`



## Weeks 4–5 – Data Cleaning and Preparation

**Script:** `scripts/week4_5_cleaning.py` · **Full output:** `results/cleaning_report.txt`

**What it does**
1. Converts CloseDate, PurchaseContractDate, ListingContractDate,
   ContractStatusChangeDate to datetime
2. Drops redundant columns – single-value columns (MlsStatus,
   OriginatingSystemName), duplicates (agent first/last name, ListingKeyNumeric,
   LotSizeArea), and agent emails (personal info)
3. Missing values – trims text, converts Y/N fields to True/False; numeric
   gaps are left blank rather than guessed so medians aren't biased
4. Confirms numeric types (prices as decimals, counts as integers)
5. **Removes** values that are always invalid: ClosePrice ≤ 0, LivingArea ≤ 0,
   DaysOnMarket < 0, negative bedrooms/bathrooms
6. **Flags** (keeps) date-order problems
7. **Flags** (keeps) bad coordinates

**Row counts**

| | Before | Missing price/date | Invalid values | After |
|---|---:|---:|---:|---:|
| Sold | 414,054 | −2 | −199 (1 price, 150 sq ft, 48 DOM) | **413,853** |
| Listings | 557,051 | – | −395 (366 sq ft, 29 DOM) | **556,656** |

**Date consistency flags** (rows kept)

| Flag | Rule | Sold | Listings |
|---|---|---:|---:|
| `listing_after_close_flag` | ListingContractDate > CloseDate | 61 | 74 |
| `purchase_after_close_flag` | PurchaseContractDate > CloseDate | 239 | 229 |
| `negative_timeline_flag` | PurchaseContractDate < ListingContractDate | 267 | 274 |

**Geographic data quality** (rows kept)

| Flag | Sold | Listings |
|---|---:|---:|
| Missing lat/long | 4,102 | 80,646 |
| Lat or long = 0 | 27 | 65 |
| Positive longitude (must be negative in CA) | 31 | 73 |
| Outside California | 64 | 230 |
| Exactly at California's center point (failed geocode) | 148 | 1 |
| **Any invalid (`invalid_coords_flag`)** | **4,341 (1.0%)** | **80,942 (14.5%)** |

**Findings**
- 148 sold homes sit at exactly 36.778, −119.418 – the center of California,
  which geocoders return when they can't find an address.
- Listing files for Jan–Aug 2024 (and sold Feb 2024) are missing coordinates
  for 20–80% of rows; every other month is ~1%. Those months never got the
  coordinate back-fill. Maps should aggregate by ZIP code (present on 99.99%
  of rows) instead of plotting points.

**Output:** `output/sold_cleaned.csv`, `output/listings_cleaned.csv`



## How to run

Put the raw `CRMLS*.csv` files in the project folder, with the scripts in a
`scripts/` subfolder, then run in order:

```
python3 scripts/week1_combine.py
python3 scripts/week2_3_eda.py
python3 scripts/week2_3_mortgage_rates.py
python3 scripts/week4_5_cleaning.py
```

Requires Python 3 with `pandas`, `matplotlib`, and `requests`.
