# Forecasting Methodology

## Ensemble Approach

One model is risky on 12 to 24 months of dealership data, so the forecast blends up to three. Every model's 12 monthly values, the weights, the library versions and the training window go into the facts file (`models` block). The workbook title names only the models that actually produced numbers.

### Model 1: Prophet
**What it does**: learns trend and seasonality from the store's own data.
```python
from prophet import Prophet

model = Prophet(
    yearly_seasonality=True,       # only with 24+ months
    weekly_seasonality=False,      # monthly data
    daily_seasonality=False,
    changepoint_prior_scale=0.05,  # conservative, prevents overfitting
    seasonality_mode='multiplicative',
    interval_width=0.80            # Prophet's own interval is not shown in the workbook
)
```
**Caution**: Prophet can extrapolate a short recent dip into a steep decline. That is why it is blended, and why the Model Confidence Check below exists.

**With only 12 months**: `yearly_seasonality=False` and a lower weight.

### Model 2: Holt-Winters Exponential Smoothing
**What it does**: trend plus seasonality plus noise.
```python
from statsmodels.tsa.holtwinters import ExponentialSmoothing

model = ExponentialSmoothing(
    data,
    seasonal_periods=12,
    trend='add',
    seasonal='mul',
    damped_trend=True      # prevents runaway trend extrapolation
)
result = model.fit(optimized=True)
forecast = result.forecast(12)
```
**Why damped**: without damping any trend runs forever; dealership leads do not grow or shrink indefinitely.

### Model 3: Seasonal prior (DigitalCLIQ estimate)
**What it is**: a fixed month-by-month shape applied to the store's average. The indices below are a DigitalCLIQ estimate with no named published source or date yet, so they are labelled "Seasonal prior (DigitalCLIQ estimate)" everywhere, never "NADA". If Drew names a source and date for them, cite it and update the label.
```python
seasonal_prior = {
    1: 0.88,   # January, post-holiday low
    2: 0.94,   # February, tax refund season starts
    3: 1.08,   # March, spring peak
    4: 1.04,
    5: 1.02,   # Memorial Day
    6: 1.00,
    7: 0.96,   # summer lull
    8: 1.03,   # model-year clearance begins
    9: 1.02,
    10: 1.05,
    11: 0.98,
    12: 1.00,
}
avg_leads = historical['total_leads'].mean()
growth = year2_total / year1_total          # when two years exist
base = avg_leads * growth
prior_forecast = [base * seasonal_prior[m] for m in range(1, 13)]
```

## Ensemble Weighting

### With 24+ months
| Model | Weight | Rationale |
|-------|--------|-----------|
| Prophet | 25% | Detects trend, may overfit short data |
| Holt-Winters | 40% | Most stable at 24 months, damped |
| Seasonal prior | 35% | Stabilizing prior (DigitalCLIQ estimate) |

### With only 12 months
| Model | Weight | Rationale |
|-------|--------|-----------|
| Prophet | 15% | No yearly seasonality possible |
| Holt-Winters | 25% | Small sample |
| Seasonal prior | 60% | Carries the seasonal shape |

These weights are a DigitalCLIQ planning assumption.

```python
ensemble = w_prophet * prophet + w_hw * hw + w_prior * prior
```

**A model that fails to fit** is dropped, not replaced by an improvised one. Renormalize the remaining weights in proportion, list only the models that ran in `models.ran`, and title the tab by what ran, e.g. "2026 Lead Forecast: 2-Model Blend (Holt-Winters + Seasonal prior)". Write "3-Model Ensemble" only when all three ran. Tell Drew which model dropped and why.

## Model Confidence Check and Sanity Rows (before any scenario is built)

Run `verify_workbook.py audit <facts.json>`. It prints:
- each model's forecast total and its gap from the ensemble;
- the ensemble total against the same months last year;
- the ensemble total against the flat average (average month of history times the horizon);
- last year's actual change.

Ask Drew, and wait for a yes, when:
1. **A model is more than 20% from the ensemble**: "Prophet is forecasting 22% above the ensemble. This usually means it detected a trend the other models do not see. Options: (a) accept current weights, (b) adjust weights, (c) investigate the driver." Rebuild the ensemble if the weights change.
2. **The ensemble is more than 10% from last year's same months or from the flat average.**
3. **The ensemble reverses last year's direction by more than 5%** (for example -9.1% after a +2.7% year).

Record each answer in `confirmations.divergence` or `confirmations.sanity` and re-run until the audit exits 0. Real declines exist; the point is that Drew sees the rows before a GM does.

## Planning Range

The workbook shows a **planning range**, not a statistical interval:
- `Planning Low (-12%) = baseline x 0.88`, `Planning High (+12%) = baseline x 1.12`;
- a line under the Forecast table reads "Planning range, not a statistical interval.";
- `forecast.interval_method` in the facts file says "fixed +/-12% planning range".

Optional, with 24+ months of history: hold out the last 12 months, refit on the earlier data, and set the half-width to max(12%, the 80th-percentile absolute monthly miss). Label it "X of the last 12 months fell inside", show the actual half-width in the Planning Low / High headers, and record the method and result in the facts file. Never call it a confidence interval.

## Budget Scenarios

### Spend elasticity (estimated, with its statistics)
Run `verify_workbook.py elasticity <facts.json>`. It regresses log monthly leads on log monthly spend over the history (standard library, runs anywhere) and prints slope, r, p, standard error, n and the 95% CI:
- label "Estimated" when p < 0.05, otherwise "Estimated, not statistically significant";
- never presented as a measurement;
- put slope, p, n and the 95% CI in the Methodology note and the Scenario Planner input label;
- a CI that crosses zero means the data cannot rule out no effect; it is not read as more spend losing leads.

Typical dealership elasticity is low, about 0.02 to 0.10 (DigitalCLIQ planning assumption), because most leads come from market demand, many platforms price per listing rather than per lead, and brand and infrastructure spend does not scale with leads.

### Scenario formulas (Scenario Planner tab)
```
Projected Leads = Baseline Leads x (1 + Budget Change % x Lead Elasticity)
Projected Sales = Projected Leads x (Baseline Sales / Baseline Leads)
```
The sales line is labelled "Assumed: close rate held at [year] level". There is no sales elasticity: do not regress sales on spend (spend rose over time while close rate fell, so that slope measures timing, not a spend effect).

Baseline Leads is the Forecast tab's baseline TOTAL. The Executive Summary scenario columns and the Forecast tab's +25% / -15% columns all read the same Scenario Planner inputs, so one baseline feeds every tab.

## Correlation Analysis

Always report, from the elasticity output:
1. correlation of log spend and log leads (r);
2. its p value (p < 0.05 = significant);
3. the elasticity slope with its 95% CI.

If the relationship is not significant (p >= 0.05), that is the headline finding: the current mix is not turning dollars into leads, so reallocation matters more than budget size.

## Sources
- Hyndman and Athanasopoulos, *Forecasting: Principles and Practice*, 3rd ed. (otexts.com/fpp3), 2021
- Prophet documentation (facebook.github.io/prophet)
- statsmodels Exponential Smoothing documentation
- Seasonal prior indices: DigitalCLIQ estimate, no published source yet
