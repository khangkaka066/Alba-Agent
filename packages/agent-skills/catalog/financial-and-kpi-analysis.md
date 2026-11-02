---
name: Financial & KPI Analysis
slug: financial-and-kpi-analysis
category: finance
description: "Practical SOPs, validation checks, and guardrails for financial & kpi analysis."
trigger_keywords: ["revenue", "margin", "cohort", "unit", "economics", "financial", "KPI"]
required_tools: ["safe_sql", "chart_generator"]
recommended_models: ["openai/gpt-4.1", "anthropic/claude-sonnet"]
---

## Purpose
Produce reconciled financial and operating metrics with transparent definitions and decision-useful caveats.

## Standard operating procedure
1. Confirm currency, accounting basis, fiscal calendar, reporting period, entity scope, and whether figures are actual, budget, or forecast.
2. Reconcile source totals to the supplied ledger or control totals. Separate recurring, one-time, cash, and non-cash items where relevant.
3. Define each KPI before calculating it: numerator, denominator, cohort, time window, inclusion rules, and treatment of refunds or churn.
4. Analyze revenue, gross margin, contribution margin, retention, CAC/LTV, payback, and unit economics only where source data supports those metrics.
5. Build cohorts with consistent start dates and age periods. Compare like-for-like cohorts; flag small denominators and survivorship effects.
6. Detect anomalies against a relevant baseline and quantify both absolute and percentage change. Check seasonality, mix shifts, and source-data changes before attributing causes.
7. Run sensitivity cases for material assumptions and show how the conclusion changes.

## Checklist
- [ ] Currency, period, accrual/cash basis, and scope are explicit.
- [ ] Every KPI formula and denominator is documented.
- [ ] Totals reconcile or differences are explained.
- [ ] Cohorts are comparable and low sample sizes are flagged.
- [ ] Anomalies are checked against seasonality and data-quality changes.

## Guardrails
Do not present forecasts as actuals or treat correlation as cause. Do not conceal unfavorable movements with selective periods. Protect customer-level financial data and round only after calculations.

## Output template
### Executive readout
Most material movement and its confidence.

### KPI table
Metric, definition, current period, comparison, variance, and source.

### Drivers and scenarios
Evidence-supported drivers and sensitivity cases.

### Risks
Data gaps, accounting assumptions, and follow-up checks.

## Golden example
For margin change, reconcile revenue and direct costs first, show the exact denominator and currency, then distinguish price, volume, and mix explanations from hypotheses that require further evidence.
