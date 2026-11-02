---
name: SQL & Database Analytics
slug: sql-and-database-analytics
category: data
description: "Practical SOPs, validation checks, and guardrails for sql & database analytics."
trigger_keywords: ["SQL", "query", "database", "schema", "aggregation"]
required_tools: ["safe_sql"]
recommended_models: ["openai/gpt-4.1-mini", "deepseek/deepseek-chat"]
---

## Purpose
Answer analytical questions from databases through bounded, read-only, auditable queries.

## Standard operating procedure
1. Confirm the authorized database and reporting scope. Inspect schema, keys, nullability, indexes, and table descriptions before writing a query.
2. Use only approved read-only connections. Select the smallest relevant tables and columns. Always include tenant/workspace scope where the schema requires it.
3. Build a simple query first, then add joins and aggregations one at a time. Verify join cardinality and check for row multiplication.
4. Use explicit date boundaries, time zones, units, and null handling. Avoid `SELECT *` on large tables.
5. Bound results with a row limit. Inspect the query plan when supported; compare index use and estimated scan size before expensive analysis.
6. Reconcile aggregates against an independent query or source total and return query assumptions with the result.

## Checklist
- [ ] Connection is read-only and authorized for this workspace.
- [ ] Tenant filters are present wherever required.
- [ ] Joins do not multiply records unexpectedly.
- [ ] Time ranges are half-open and timezone-aware where appropriate.
- [ ] Results are bounded and key totals are validated.

## Guardrails
Never issue data-changing statements, schema changes, grants, file operations, or multi-statement SQL. Do not expose credentials or unrestricted row-level personal data. Stop if the data scope is unclear.

## Output template
### Result
Metric/table with units and scope.

### Query method
Tables, joins, filters, aggregation, and date boundaries.

### Validation
Row counts, reconciliations, and query plan notes.

## Golden example
Before joining orders to line items, calculate rows per order and aggregate line items to order grain; then join and compare total revenue to the source control total to catch multiplication.
