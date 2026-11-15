# IDX Exchange Internship – MLS Data Pipeline

Python pipeline that turns monthly California MLS (CRMLS) exports into clean,
analysis-ready datasets for market analytics and Tableau dashboards.

Data: 56 monthly CSV files, January 2024 – April 2026
(28 listing files + 28 sold files) from the CoreLogic Trestle API via IDX Exchange.
The raw data is confidential MLS data and is not included in this repo.

## Row counts at a glance

| Stage | Sold rows | Listing rows | Script |
|---|---:|---:|---|
| Raw monthly files combined (all property types) | 615,707 | 872,785 | Week 1 |
| After PropertyType == 'Residential' filter | 414,054 | 557,051 | Week 1 |
| After dropping >90%-empty columns | 414,054 | 557,051 | Weeks 2–3 EDA |
| After merging mortgage rates | 414,054 | 557,051 | Weeks 2–3 rates |
| After cleaning (final analysis-ready data) | 413,853 | 556,656 | Weeks 4–5 |
| After adding market metrics and school districts | 413,853 | – | Week 6 |
| Full flagged dataset (outlier flags added) | 413,853 | – | Week 7 |
| Filtered analysis dataset (outliers and duplicate copies left out) | 348,591 | – | Week 7 |

| Stage | Sold columns | Listing columns |
|---|---:|---:|
| Week 1 combined | 85 | 74 |
| Weeks 2–3 after dropping empty columns | 70 | 59 |
| Weeks 2–3 after adding mortgage rate | 72 | 61 |
| Weeks 4–5 cleaned (redundant columns out, flag columns in) | 74 | 65 |
| Week 6 with market metrics and school districts | 86 | – |

## Week 0 – Data Pipeline Orientation

Monthly files were downloaded from the IDX Exchange FTP. Three listing files
(Jan 2024, Mar 2024, Jan 2026) were cut off mid-download – e.g. March 2024
had 8,030 rows instead of ~25,000 – so they were re-extracted from the Trestle
API. Because the API returns records added after the FTP files were generated,
listing counts can be slightly higher than other interns' (sold counts match).

## Week 1 – Monthly Dataset Aggregation

Script: scripts/week1_combine.py

What it does
- Loads every CRMLSListingYYYYMM.csv and CRMLSSoldYYYYMM.csv from Jan 2024
  to the latest month in the folder and stacks them with pd.concat
- Uses the *_filled.csv version of a sold month when one exists
  (those have back-filled latitude/longitude)
- Drops 11 duplicate columns in the listing files (e.g. ListPrice.1), caused
  by the extraction script requesting those fields twice
- Warns if a file looks truncated (doesn't end with a newline)
- Filters both datasets to PropertyType == 'Residential'

Row counts

| | Before concat | After concat | After Residential filter | % kept |
|---|---|---:|---:|---:|
| Sold | 28 files, 16,487–26,487 rows each | 615,707 | 414,054 | 67.2% |
| Listings | 28 files, 18,773–40,271 rows each | 872,785 | 557,051 | 63.8% |

Output: output/combined_sold_residential.csv, output/combined_listings_residential.csv

## Weeks 2–3 – Dataset Structuring, Validation & EDA

Script: scripts/week2_3_eda.py · Full output: results/eda_report.txt

What it does and what the outputs show

1. Property types – counts every PropertyType in the raw files
   (results/property_type_counts.csv). Residential is 67.2% of sold records
   and 63.8% of listings. The rest is mostly ResidentialLease (rentals, 22.9%),
   Land, and ManufacturedInPark, which are excluded because they price differently.
2. Structure – rows, columns, and data type of every column.
3. Missing values – null count and % for every column
   (results/null_summary_sold.csv, results/null_summary_listings.csv).
   15 columns are >90% empty in each dataset and are dropped
   (e.g. TaxAnnualAmount, BuilderName, AboveGradeFinishedArea).
   Core fields like price, size, and dates are kept even if partially missing.
4. Numeric distributions – min, max, mean, median, and percentiles for
   ClosePrice, ListPrice, OriginalListPrice, LivingArea, LotSizeAcres,
   BedroomsTotal, BathroomsTotalInteger, DaysOnMarket, YearBuilt
   (results/numeric_summary_sold.csv), plus a histogram and boxplot for each
   (results/plots/). Extreme outliers flagged for later: 40 sales ≥ $100M
   (data-entry errors, max $990M), 207 homes ≤ 100 sq ft, 48 negative DOM.

EDA questions answered

| Question | Answer |
|---|---|
| Residential share | 67.2% of sold, 63.8% of listings |
| Median / average close price | $823,000 / $1,193,864 (right-skewed by luxury sales) |
| Days on market | Median 18, mean 37.4; 63% sell within 30 days |
| Sold above / at / below list | 40.1% / 17.4% / 42.5% |
| Date problems | 61 closed before listing (0.01%), 239 closed before contract |
| Highest median price counties | San Mateo $1.70M, Santa Clara $1.60M, Santa Cruz $1.20M (results/county_median_price.csv) |

Row counts: unchanged (414,054 sold, 557,051 listings) – this step removes
columns, not rows. Sold 85 → 70 columns, listings 74 → 59.

Output: output/sold_residential_filtered.csv, output/listings_residential_filtered.csv

## Weeks 2–3 – Mortgage Rate Enrichment

Script: scripts/week2_3_mortgage_rates.py

What it does
1. Downloads the FRED MORTGAGE30US series (30-year fixed rate, weekly)
2. Averages it to one rate per month (results/mortgage30us_monthly.csv)
3. Adds a year_month key – from CloseDate for sold, ListingContractDate for listings
4. Left-joins the monthly rate onto both datasets
5. Validates: row counts unchanged and 0 null rates in either dataset

Row counts: unchanged – 414,054 sold, 557,051 listings (+2 columns:
year_month, rate_30yr_fixed). Rates in the data range from 6.05%
(Feb 2026) to 7.06% (May 2024).

Output: output/sold_with_rates.csv, output/listings_with_rates.csv

## Weeks 4–5 – Data Cleaning and Preparation

Script: scripts/week4_5_cleaning.py · Full output: results/cleaning_report.txt

What it does
1. Converts CloseDate, PurchaseContractDate, ListingContractDate,
   ContractStatusChangeDate to datetime
2. Drops redundant columns – single-value columns (MlsStatus,
   OriginatingSystemName), duplicates (agent first/last name, ListingKeyNumeric,
   LotSizeArea), and agent emails (personal info)
3. Missing values – trims text, converts Y/N fields to True/False; numeric
   gaps are left blank rather than guessed so medians aren't biased
4. Confirms numeric types (prices as decimals, counts as integers)
5. Removes values that are always invalid: ClosePrice ≤ 0, LivingArea ≤ 0,
   DaysOnMarket < 0, negative bedrooms/bathrooms
6. Flags (keeps) date-order problems
7. Flags (keeps) bad coordinates
8. Flags (keeps) older copies of listings that appear in more than one monthly file

Row counts

| | Before | Missing price/date | Invalid values | After |
|---|---:|---:|---:|---:|
| Sold | 414,054 | −2 | −199 (1 price, 150 sq ft, 48 DOM) | 413,853 |
| Listings | 557,051 | – | −395 (366 sq ft, 29 DOM) | 556,656 |

Date consistency flags (rows kept)

| Flag | Rule | Sold | Listings |
|---|---|---:|---:|
| listing_after_close_flag | ListingContractDate > CloseDate | 61 | 74 |
| purchase_after_close_flag | PurchaseContractDate > CloseDate | 239 | 229 |
| negative_timeline_flag | PurchaseContractDate < ListingContractDate | 267 | 274 |

Geographic data quality (rows kept)

| Flag | Sold | Listings |
|---|---:|---:|
| Missing lat/long | 4,102 | 80,646 |
| Lat or long = 0 | 27 | 65 |
| Positive longitude (must be negative in CA) | 31 | 73 |
| Outside California | 64 | 230 |
| Exactly at California's center point (failed geocode) | 148 | 1 |
| Any invalid (invalid_coords_flag) | 4,341 (1.0%) | 80,942 (14.5%) |

Duplicate ListingKeys (rows kept)

| | Sold | Listings |
|---|---:|---:|
| ListingKeys appearing more than once | 337 | 158 |
| Older copies flagged (duplicate_listingkey_flag) | 341 | 160 |
| Unique listings after excluding flagged copies | 413,512 | 556,496 |

The same listing shows up in two monthly files when the MLS record was updated
after the first export. The newest copy is kept unflagged.

Findings
- 148 sold homes sit at exactly 36.778, −119.418 – the center of California,
  which geocoders return when they can't find an address.
- Listing files for Jan–Aug 2024 (and sold Feb 2024) are missing coordinates
  for 20–80% of rows; every other month is ~1%. Those months never got the
  coordinate back-fill. Maps should aggregate by ZIP code (present on 99.99%
  of rows) instead of plotting points.

Output: output/sold_cleaned.csv, output/listings_cleaned.csv

## Week 6 – Feature Engineering and Market Metrics

Script: scripts/week6_features.py · Full output: results/feature_report.txt

What it does
1. Adds market metrics to the cleaned sold data

| New column | Formula | Purpose |
|---|---|---|
| price_ratio | ClosePrice / ListPrice | Negotiation strength vs. final asking price |
| close_to_original_list_ratio | ClosePrice / OriginalListPrice | Captures every price cut since first listing |
| price_per_sqft | ClosePrice / LivingArea | Normalizes price across home sizes |
| DaysOnMarket | Raw MLS field (kept as is) | Time to sell |
| close_year, close_month, close_yrmo | From CloseDate | Time-series analysis (close_yrmo like 2024-01) |
| listing_to_contract_days | PurchaseContractDate − ListingContractDate | Time from listing to accepted offer |
| contract_to_close_days | CloseDate − PurchaseContractDate | Escrow / closing period |

   Ratios only use valid denominators (> 0); otherwise they are left blank.

2. Assigns each home to its school district by latitude/longitude using the
   California School District Areas 2024-25 boundaries (California Department
   of Education). California has unified (K-12) districts plus separate,
   overlapping elementary and high school districts, so each home gets either
   a unified district or an elementary + high school district:
   school_district_unified, school_district_elementary, school_district_high,
   and school_district (unified if there is one, otherwise elementary).
   Homes with invalid coordinates from Weeks 4–5 get no district.
   Result: 409,393 of the 409,512 homes with usable coordinates (99.97%)
   matched a district – 309,548 in a unified district, 101,523 in an
   elementary district and 99,471 in a high school district. 4,460 homes have
   no district (bad or missing coordinates).

3. Segment summary tables – medians, one row per listing (older duplicate
   copies left out), by:
   - PropertyType / PropertySubType
   - County, and county + MLS area
   - School district
   - Listing office and buyer office (units and sales volume)

   Highlights: single-family homes are 309,302 of the sales (median $895,000);
   the highest-priced school districts are Hillsborough City Elementary
   ($5.35M median), Rancho Santa Fe Elementary ($5.0M) and Saratoga Union
   Elementary ($4.25M). Summary tables: results/segment_property_type.csv,
   results/segment_county.csv, results/segment_school_district.csv.

Row counts: unchanged at 413,853 sold rows; 12 new columns (74 → 86).

Output: output/sold_features.csv, output/week6/segment_*.csv

## Week 7 – Outlier Detection and Data Quality

Script: scripts/week7_outliers.py · Full output: results/outlier_report.txt

What it does – a tiered approach: flag first, keep the raw records, and build a
separate filtered dataset.

1. Tier 1 – business rules. ClosePrice ≤ 0, LivingArea ≤ 0 and DaysOnMarket < 0
   are always invalid (all 0 here – removed in Weeks 4–5). New: a price ratio
   below 0.5 or above 2 means the list price was entered wrong (e.g. an original
   list price of $1). 1,343 sales get ratio_entry_error_flag (302 on
   price_ratio, 1,335 on close_to_original_list_ratio); the sale is kept
   and the bad ratio is blanked in the filtered dataset.
2. Tier 2 – IQR flags. For each field: IQR = Q3 − Q1, lower = Q1 − 1.5 × IQR,
   upper = Q3 + 1.5 × IQR. Rows outside the bounds get <field>_outlier_flag.
   1st/99th percentiles are shown next to each bound (results/iqr_bounds.csv).

| Field | Upper bound | Flagged | Use |
|---|---:|---:|---|
| ClosePrice | $2,387,500 | 30,715 (7.4%) | flag + filter |
| LivingArea | 3,676 sq ft | 18,207 (4.4%) | flag + filter |
| DaysOnMarket | 108 days | 31,772 (7.7%) | flag + filter |
| price_per_sqft | $1,278 | 17,454 (4.2%) | flag only |
| close_to_original_list_ratio | 0.86 – 1.12 | 38,243 (9.2%) | flag only |

   Lower bounds for price, size and days on market are negative, so IQR only
   flags the high end. The ratio is flag-only because at 1.5 × IQR it catches
   normal homes that had a 15%+ price cut, which is real market behavior.

3. Tier 3 – filtered dataset: leaves out rows flagged on ClosePrice,
   LivingArea or DaysOnMarket (64,971) and older duplicate copies of a listing
   (291).

Row counts

| | Rows |
|---|---:|
| Full flagged dataset | 413,853 |
| Outlier on ClosePrice, LivingArea or DaysOnMarket | −64,971 |
| Older duplicate copy of a listing | −291 |
| Filtered dataset | 348,591 (84.2%) |

Before vs. after filtering (results/before_after_comparison.csv)

| | Median before | Median after | Mean before | Mean after |
|---|---:|---:|---:|---:|
| ClosePrice | $823,000 | $785,000 (−4.6%) | $1,193,067 | $899,011 (−24.6%) |
| LivingArea | 1,643 | 1,569 | 1,905 | 1,675 |
| DaysOnMarket | 18 | 16 | 37.4 | 26.3 |
| price_per_sqft | $537 | $527 | $650 | $568 |

Findings
- The mean close price drops 25% but the median only 5%: a few very expensive
  sales (up to $989.5M, a data-entry error) pull the mean up, so dashboards
  should report medians.
- The IQR bounds are statewide. Most ClosePrice outliers are ordinary homes in
  high-cost counties (Los Angeles 9,351, Orange 5,567, Santa Clara 4,422), so
  county-level analysis of expensive areas should use the full flagged dataset
  or per-county bounds.

Output: output/sold_flagged.csv (all rows + 8 flag columns), output/sold_filtered.csv

## How to run

Put the raw CRMLS*.csv files in the project folder, with the scripts in a
scripts/ subfolder, then run in order:

```
python3 scripts/week1_combine.py
python3 scripts/week2_3_eda.py
python3 scripts/week2_3_mortgage_rates.py
python3 scripts/week4_5_cleaning.py
python3 scripts/week6_features.py
python3 scripts/week7_outliers.py
```

Requires Python 3 with pandas, matplotlib, and requests.
