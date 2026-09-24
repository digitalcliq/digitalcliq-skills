# Forecasting Methodology

## 3-Model Ensemble Approach

Using a single model is risky with limited dealership data (12-24 months). An ensemble averages out individual model weaknesses.

### Model 1: Facebook Prophet
**What it does**: Detects trends and seasonality from the data itself.
**Configuration**:
```python
from prophet import Prophet

model = Prophet(
    yearly_seasonality=True,       # Enable if 24+ months
    weekly_seasonality=False,      # Monthly data, no weekly
    daily_seasonality=False,       # Monthly data, no daily
    changepoint_prior_scale=0.05,  # Conservative — prevents overfitting
    seasonality_mode='multiplicative',  # Seasonal effects scale with level
    interval_width=0.80            # 80% confidence intervals
)
```
**Caution**: Prophet can extrapolate trends aggressively with limited data. If it detects a downward trend in the last few months, it may project a steep decline that isn't realistic. This is why we ensemble it with more stable models.

**With only 12 months**: Set `yearly_seasonality=False` (not enough data to detect it). Reduce weight in ensemble.

### Model 2: Holt-Winters Exponential Smoothing
**What it does**: Classic time-series decomposition into trend + seasonality + noise.
**Configuration**:
```python
from statsmodels.tsa.holtwinters import ExponentialSmoothing

model = ExponentialSmoothing(
    data,
    seasonal_periods=12,
    trend='add',           # Additive trend
    seasonal='mul',        # Multiplicative seasonality
    damped_trend=True      # IMPORTANT: prevents runaway trend extrapolation
)
result = model.fit(optimized=True)
forecast = result.forecast(12)
```
**Why damped trend**: Without damping, any trend detected in the data continues forever. Damping gradually flattens the trend, which is more realistic for dealership leads (they don't grow or shrink indefinitely).

### Model 3: NADA Seasonal Benchmark
**What it does**: Applies industry-standard seasonal patterns from NADA (National Automobile Dealers Association) data.
**Seasonal Indices for Luxury/Import Dealers**:
```python
nada_seasonal = {
    1: 0.88,   # January — post-holiday low
    2: 0.94,   # February — tax refund season starts
    3: 1.08,   # March — spring selling season peak
    4: 1.04,   # April — strong
    5: 1.02,   # May — Memorial Day push
    6: 1.00,   # June — baseline
    7: 0.96,   # July — summer doldrums
    8: 1.03,   # August — model year clearance begins
    9: 1.02,   # September — new model year arrivals
    10: 1.05,  # October — strong fall
    11: 0.98,  # November — pre-holiday pause
    12: 1.00,  # December — year-end push
}
```
**Application**:
```python
# Use the dealer's average monthly leads as base
avg_leads = historical_data['total_leads'].mean()
# Apply YoY growth rate if available
yoy_growth = year2_total / year1_total
base_2026 = avg_leads * yoy_growth
# Project each month
nada_forecast = [base_2026 * nada_seasonal[m] for m in range(1, 13)]
```

## Ensemble Weighting

The weights depend on how much data is available:

### With 24+ months (recommended):
| Model | Weight | Rationale |
|-------|--------|-----------|
| Prophet | 25% | Can detect trends but may overfit with limited data |
| Holt-Winters | 40% | Most stable with 24 months, damped trend prevents runaway |
| NADA Seasonal | 35% | Industry benchmark provides strong prior |

### With only 12 months:
| Model | Weight | Rationale |
|-------|--------|-----------|
| Prophet | 15% | Cannot detect yearly seasonality, trend-only |
| Holt-Winters | 25% | Limited by small sample |
| NADA Seasonal | 60% | Industry data compensates for limited dealer data |

### Ensemble Calculation
```python
ensemble = (w_prophet * prophet_forecast + 
            w_hw * hw_forecast + 
            w_nada * nada_forecast)
```

## Budget Scenario Modeling

Use the measured spend elasticity to project leads under different budget levels.

### Spend Elasticity
```python
from scipy import stats
import numpy as np

log_spend = np.log(monthly['total_spend'])
log_leads = np.log(monthly['total_leads'])
slope, intercept, r_val, p_val, std_err = stats.linregress(log_spend, log_leads)
elasticity = slope
# Interpretation: 10% more spend → (elasticity × 10)% more leads
```

**Typical dealership elasticity**: 0.02–0.10. This is LOW — meaning budget increases have minimal impact on lead volume. This is normal and expected because:
1. Most leads come from market demand, not dealer spend
2. 3rd-party platforms have fixed pricing (you pay per listing, not per lead)
3. Brand/infrastructure spend doesn't scale linearly with leads

### Scenario Formulas (for Excel Scenario Planner tab)
```
Projected Leads = Baseline Leads × (1 + Budget Change % × Elasticity)
Projected Sales = Baseline Sales × (1 + Budget Change % × Sales Elasticity)
```
Where Sales Elasticity is typically ~50% of Lead Elasticity (budget affects volume more than quality).

## Confidence Intervals

Use 80% confidence intervals (not 95%) because:
- 12-24 months is limited data
- 80% gives a useful range without being so wide it's meaningless
- For the ensemble: `lower = forecast × 0.88`, `upper = forecast × 1.12`

## Correlation Analysis

Always calculate and report:
1. **Pearson correlation** between monthly spend and monthly leads
2. **p-value** for statistical significance (p < 0.05 = significant)
3. **Spend elasticity** (log-log regression slope)

If correlation is NOT significant (p > 0.05), this is the MOST IMPORTANT FINDING to report. It means the current budget mix isn't efficiently converting dollars to leads, and reallocation matters more than budget size.

## Sources
- Hyndman & Athanasopoulos, *Forecasting: Principles and Practice*, 3rd ed. (otexts.com/fpp3)
- Facebook/Meta Prophet documentation (facebook.github.io/prophet)
- NADA Annual Data Reports (nada.org)
- statsmodels Exponential Smoothing documentation
