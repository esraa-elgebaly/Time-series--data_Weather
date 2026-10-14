# Cairo Weather: Can We Forecast Tomorrow?

Time-series EDA and forecasting setup for **Cairo, Egypt**, using 36 years of daily data (1990–2025) from the **NASA POWER API**.

**Goal:** understand the data well enough to forecast two things for tomorrow:

| Target | Type | Definition |
|---|---|---|
| Mean temperature | Regression | `temp_mean` of the next day (°C) |
| Rain | Classification | Next day has ≥ 1 mm of rain (yes / no) |

![Max temperature, every day since 1990](figures/04_daily_max_temperature_heatmap.png)

---

## Data

| | |
|---|---|
| **Source** | [NASA POWER](https://power.larc.nasa.gov/) daily point API (free, no API key) |
| **Location** | Central Cairo, 30.04° N, 31.24° E |
| **Period** | 1990-01-01 to 2025-12-31 (13,149 days, no gaps, no duplicates) |
| **Variables** | Mean, max and min temperature, rain, humidity, wind speed, wind direction, pressure |

**Rules followed:** the raw data is never changed, no rows are dropped, wrong values become `NaN`, only short gaps (≤ 3 days) are filled, real extreme days are kept, and anything learned from the data uses training years only.

---

## Key findings

### 1. The data looked clean, but hid two problems
- **Wind direction** is wrong from 2013 to 2025 (values down to −9000°): 36 % of the column. Left empty, not invented; valid for 1990–2012 only.
- **Rain** jumps suddenly in 2016 (tested as H3 below).

![Missing wind direction per year](figures/02_missing_wind_direction.png)

### 2. The season controls everything
The mean temperature goes from about 12 °C in January to 30 °C in July–August, a seasonal swing of **19.1 °C**. Rain falls from October to April, and hotter days are drier.

![Cairo climate overview](figures/03_cairo_climate_overview.png)

### 3. Hypotheses

| # | Question | Answer |
|---|---|---|
| **H1** | Is Cairo warming, and are nights warming faster than days? | **Yes.** Nights +0.41 °C and days +0.23 °C per 10 years |
| **H2** | Are very hot days (> 40.1 °C) becoming more frequent? | **Partly.** 7 in 2013 vs 38 in 2024; 2023–2024 are the most extreme |
| **H3** | Did heavy rain really increase after 2016, or did the data change? | **Most likely the data.** See below |
| **H4** | Are cold waves (< 5.7 °C) becoming rarer? | **Yes, slowly.** 20.4 per year (1990s) to 15.5 (2020s) |
| **H5** | Do storms show warning signs in the days before? | **Partly.** Heat waves and cold snaps build up; storms don’t |
| **H6** | Can Khamasin-like days be detected? | **Yes.** 125 days in 1990–2012, mostly December to April |

![H1: yearly mean of max and min temperature](figures/05_h1_yearly_max_min.png)

### 4. H3: did it really rain more after 2016?

| | 1990–2015 | 2016–2025 |
|---|---|---|
| Rain days (≥ 1 mm) per year | 8.1 | 17.6 |
| Heavy rain days (≥ 10 mm) per year | 0.1 | 3.8 |
| Total rain per year | 30.6 mm | 142 mm |

Three reasons this is most likely a change in the data, not the weather:
1. **Sudden:** the jump happens at one year, not as a slow rise.
2. **Unrealistic:** 142 mm a year vs Cairo’s normal of about 20–25 mm.
3. **Storms did not get stronger:** a storm score built from consistent signs (pressure drop, wind, temperature drop, humidity) stays flat, and 7 of the 10 strongest storms are before 2016.

**Decision:** all rain work uses 2016–2025 only.

![Rain per year before vs after 2016](figures/09_h3_rain_before_after_2016.png)
![Storms vs rain over 36 years](figures/10_h3_storms_vs_rain.png)

### 5. Time-series structure
- **Decomposition (additive):** season 19.1 °C, trend 2.8 °C, daily residual 2.2 °C.
- **Stationarity (ADF):** raw, deseasonalized and differenced series are all stationary (p < 0.001).
- **Autocorrelation:** 0.97 with yesterday (0.77 with the season removed); for daily changes only the last ~5 days matter. After a rain day, rain tomorrow is 39 % likely vs 5 % normally.

![ACF and PACF](figures/12_acf_pacf.png)

---

## From EDA to the model

| What we found | What we do |
|---|---|
| A strong, fixed yearly season | Day of year as sine and cosine |
| Temperature returns to its level (ADF) | No differencing |
| Only the last few days help | Lags 1–5; no lag 365 |
| Slow warming; the test years are the warmest | Watch for a cold bias on test |
| Spring is the most unstable season | Report errors by month |
| Humidity and pressure add information | Use them as inputs |
| Rain is rare and changed in 2016 | Rain yes/no on 2016–2025, judged by F1 and CSI |
| Wind direction stops in 2012 | Not used |
| Outliers are real weather | Keep them |

## Baselines to beat

Split by time, never at random:

| | Temperature | Rain |
|---|---|---|
| Train | 1990–2019 | 2016–2020 |
| Validation | 2020–2022 | 2021–2022 |
| Test | 2023–2025 | 2023–2025 |

| Temperature baseline | MAE validation (°C) | MAE test (°C) |
|---|---|---|
| **Persistence (tomorrow = today)** | **1.07** | **1.04** |
| Mean of last 7 days | 1.59 | 1.54 |
| Climatology (normal for the date) | 1.84 | 1.79 |
| Same day last year | 2.56 | 2.27 |

For rain, “always no rain” is 94–96 % accurate but catches 0 rain days, so accuracy is not used. The best baseline is **persistence (rain today → rain tomorrow): F1 0.36 on validation, 0.47 on test.**

**A model must beat about 1.05 °C MAE to be useful.**

---

## Next steps
1. **Data for deployment:** pull the same variables from Open-Meteo, so the model is trained on the same source it uses live.
2. **Features:** day of year (sine, cosine), the last 1–5 days, humidity and pressure.
3. **Models:** Ridge, gradient boosting and SARIMAX for temperature; logistic regression for rain.
4. **Validation:** walk-forward, one year at a time; the test years are used once.
5. **Deploy** only if a model clearly beats the baselines.

## Limitations
- **Model data, not a station:** values are averages over about 50 × 50 km, so extremes may look milder.
- **Rain** is the weakest variable: only 2016–2025 is usable, and the test period has only 43 rain days.
- **Wind direction** is valid for 1990–2012 only.

---

## Repository structure

```
cairo-weather-forecasting/
├── Weather_Predication.ipynb   # full analysis: collection, cleaning, EDA, baselines
├── figures/                    # key figures used in this README and the presentation
├── presentation/               # slides (PDF)
├── requirements.txt
└── README.md
```

## How to run

```bash
pip install -r requirements.txt
jupyter notebook Weather_Predication.ipynb
```

The notebook calls the NASA POWER API once and saves the raw JSON and CSV files next to it, so no data files are stored in this repository.

## Author
**Esraa** · Machine Learning Engineer
