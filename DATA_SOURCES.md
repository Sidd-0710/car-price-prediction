# Data sources

The model is trained on `data/used_cars_india.csv`, built by `python build_dataset.py` from four
public Kaggle datasets of Indian used-car listings collected in 2025 and 2026. The raw downloads
are saved in `data/raw/` (not committed; the builder downloads them from Kaggle's public API when they are
missing, no account needed). The cleaned result, `data/used_cars_india.csv`, is committed, so the app and the
tests work straight after cloning.

| Source file | Kaggle dataset | Platform | Collected | Rows read | Licence |
|---|---|---|---|---|---|
| `cardekho_2026.zip` | [sumangoudakaggle/second-hand-car-dataset-cardekho](https://www.kaggle.com/datasets/sumangoudakaggle/second-hand-car-dataset-cardekho) | CarDekho | 2026 (files dated 30 Apr 2026; cars registered up to 2026) | 13,361 unique listings | MIT |
| `cardekho_2025.zip` | [pankajmaulekhi/indian-second-hand-cars-dataset](https://www.kaggle.com/datasets/pankajmaulekhi/indian-second-hand-cars-dataset) | CarDekho | 2025 (file dated 31 Aug 2025) | 10,145 | CC0 |
| `spinny_2025.zip` | [abhiramasdf/indian-used-cars-dataset](https://www.kaggle.com/datasets/abhiramasdf/indian-used-cars-dataset) | Spinny | Jan–Aug 2025 (listing dates in the file) | 8,095 | MIT |
| `cars24_2025.zip` | [sukhmansaran/used-cars-prices-cars-24](https://www.kaggle.com/datasets/sukhmansaran/used-cars-prices-cars-24) | Cars24 | 2025 (file dated 27 Jul 2025) | 8,839 | Apache 2.0 |

## Why these four

They are the only public Indian datasets found that are both **recent** (2025–2026) and include the
**variant / trim** of each car (VXI, ZXI Plus AMT, HTX IVT…). A larger 57,480-row dataset
(shashi0dev, Dec 2025) was considered but not used because it has no variant column.

## What the builder does

1. Reads each source and maps it to the same columns: Platform, Listing_Year, Brand, Model,
   Variant, Year, Kms_Driven, Fuel_Type, Transmission, Owner (previous owners, 0–3), City,
   Selling_Price (lakhs).
2. Harmonises names: "Maruti", "MARUTI" and "Maruti Suzuki" are one brand; "Wagon R 1.0",
   "New Wagon R" and "Wagon R" are one model; "ZXi Plus AMT" and "zxi-plus-amt" are one variant.
3. Removes rows it cannot use (see `data/build_report.json` for exact counts):
   no recognisable brand, missing values, LPG cars (removed on request), fuels with fewer than 80
   listings (hybrid), prices outside ₹0.5–500 lakh, odometers above 5,00,000 km.
4. Removes **duplicates**: the same car (brand, model, year, km, fuel, gearbox, price) listed
   twice, including CarDekho listings repeated under several cities.

Result: **36,919 listings**, 38 brands, 424 models, about 5,100 variants, registered 2001–2026
(including 1,707 cars from 2024, 411 from 2025 and 12 from 2026).

## Limitations

- Listings are **asking prices**, not final sale prices. Each platform has its own price level
  (in this data, Cars24 lists the same car slightly below CarDekho); the model uses the platform as an input.
- Each source is a snapshot; the data is not a continuous feed. 2025–2026 cars are still few
  compared with older ones, simply because few such cars are for sale second-hand yet.
- The scraped data belongs to the original platforms; these Kaggle mirrors are shared for
  research and education. Check the original terms before any commercial use.

## Older data (not published)

The previous version of this project used two older datasets (4,340 listings up to 2020, and the original
301-row dataset). They came from other repositories whose licence for the underlying listings is unclear, so they
are **not included in this repository**; they are not needed to run or retrain anything.
