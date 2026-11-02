---
name: Python Data Science & Visualization
slug: python-data-science-and-visualization
category: data
description: "Practical SOPs, validation checks, and guardrails for python data science & visualization."
trigger_keywords: ["CSV", "pandas", "statistics", "visualization", "chart"]
required_tools: ["document_parser", "chart_generator", "sandbox_shell"]
recommended_models: ["openai/gpt-4.1", "google/gemini-2.5-pro"]
---

## Purpose
Turn tabular files into reproducible, checked analysis and clear visualizations.

## Standard operating procedure
1. Inspect filenames, encodings, delimiters, sheet names, headers, row counts, types, and duplicate keys before transformation. Never overwrite the source.
2. For CSV decoding, try UTF-8 with BOM handling (`utf-8-sig`), then inspect likely encodings such as `cp1252` or `latin-1`; record the choice and check for replacement characters.
3. Profile nulls, invalid values, duplicate rows, date ranges, units, and outliers. Keep missingness distinct from zero and do not silently drop records.
4. Build transformations as explicit, repeatable steps. Validate row counts and key totals before and after each material filter or join.
5. Use pandas for bounded tabular work. State formulas, denominators, date windows, and assumptions. Check summary values independently with a simple aggregation.
6. Create charts with labeled axes, units, readable scales, color-blind-conscious colors, and a title that states the comparison. Export high-resolution output and a data table when useful.
7. Save scripts, cleaned outputs, and charts as separate run artifacts; summarize the method and limits.

## Checklist
- [ ] Source file remains unchanged and parsing choices are recorded.
- [ ] Nulls, duplicates, data types, and unexpected ranges are reviewed.
- [ ] Derived metrics reconcile to source totals and sample rows.
- [ ] Chart scales do not exaggerate differences; units and periods are visible.
- [ ] Re-running the same steps yields the same result.

## Guardrails
Do not infer sensitive attributes or reveal raw personal data in charts. Do not impute values without declaring the method. Never claim causality from descriptive comparisons alone.

## Output template
### Data quality
Files, schema, parsing, coverage, and material issues.

### Analysis
Definitions, formulas, key results, and validation checks.

### Deliverables
Artifact paths for charts, tables, and reproducible code.

### Limitations
Missingness, bias, uncertainty, and unsupported conclusions.

## Golden example
When UTF-8 decoding fails, test `utf-8-sig`, then `cp1252`; compare suspicious characters and headers, record the selected encoding, and verify row count and numeric totals before analysis.
