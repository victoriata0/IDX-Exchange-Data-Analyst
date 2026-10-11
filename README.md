# IDX Exchange Internship – MLS Data Pipeline

California MLS (CRMLS) listing and sold data, January 2024 – April 2026
(56 monthly files: 28 listing + 28 sold).

## Deliverables

| Week | Script | What it does |
| 1 | `scripts/week1_combine.py` | Concatenates all monthly files, filters to `PropertyType == 'Residential'`, saves combined CSVs. Row counts are logged in comments at the bottom. |
| 2–3 | `scripts/week2_3_eda.py` | Property types, filter logic, null-count table, >90% missing flags, numeric distributions (histograms, boxplots, percentiles), EDA questions. |
| 2–3 | `scripts/week2_3_mortgage_rates.py` | Fetches FRED MORTGAGE30US, resamples weekly → monthly, merges onto sold and listings by `year_month`, validates no null rates. |

## Results

- `results/eda_report.txt` – full EDA output
- `results/plots/` – histogram + boxplot for each key numeric field
- `results/*.csv` – null summaries, numeric summary, property type counts, county median prices, monthly mortgage rates

## Key numbers

- Listings: 872,785 → 557,051 Residential · Sold: 615,707 → 414,054 Residential
- Median close price $823,000 (mean $1,193,864) · median 18 days on market
- 40.1% sold above list, 17.4% at list, 42.5% below

## Run order

```
python3 scripts/week1_combine.py
python3 scripts/week2_3_eda.py
python3 scripts/week2_3_mortgage_rates.py
```

The raw MLS CSVs are not included in this repo (size and data licensing).
Scripts expect them in the folder one level above `scripts/`.
