# DataClarity - Stage Contracts

The single source of truth for how the five stages talk to each other. Every
stage reads contract files written by earlier stages and writes its own. No stage
imports another stage (`CLAUDE.md` 3.1). Pydantic models mirroring this document
live in `contracts/` and are the only shared import.

## 1. Run directory layout

Every upload creates a run: `runs/<run_id>/`

```
runs/<run_id>/
├── raw.csv                 # stage 1 input: the user's uploaded file
├── profile.json            # stage 1 output A: statistical profile
├── schema_inference.json   # stage 1 output B: AI semantic types + mapping
├── plan_proposed.json      # stage 1 output C: AI cleaning plan
├── plan_final.json         # stage 1 output D: the plan the USER approved
├── cleaned.csv             # stage 1 output E: clean data
├── cleaning_report.json    # stage 1 output F: what actually changed
├── metrics.json            # stage 2 output
├── diagnosis.json          # stage 3 output
├── forecast.json           # stage 4 output
├── report.json             # stage 5 output (data layer)
└── report.html             # stage 5 output (presentation layer)
```

Rules:
- A stage fails fast with a clear error if an input contract file is missing.
- Contract files are append-only per run: a stage never edits a file it did not
  write. Re-running a stage overwrites only its own outputs.
- Every contract file carries `schema_version` (string, starts at `"1.0"`) and
  `generated_at` (ISO 8601). Readers reject unknown major versions.

## 2. `profile.json` (stage 1 -> stage 1 AI, and reference for all later stages)

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-09-18T04:12:00Z",
  "dataset": {
    "rows": 152430,
    "columns": 9,
    "duplicate_rows": 12,
    "missing_cells_pct": 2.7,
    "encoding_used": "utf-8",
    "delimiter": ","
  },
  "columns": [
    {
      "name": "Unit Price",
      "dtype": "float64",
      "null_count": 6402,
      "null_pct": 4.2,
      "unique_count": 812,
      "min": -3.5,
      "max": 4500.0,
      "mean": 12.84,
      "median": 8.5,
      "q1": 3.2,
      "q3": 18.9,
      "top_values": [{"value": "9.99", "count": 3201}],
      "sample_values": ["9.99", "12.50", null, "-3.50"]
    }
  ]
}
```
Numeric-only fields (`min`, `max`, `mean`, `median`, `q1`, `q3`) are `null` for
non-numeric columns. `top_values` is capped at 10 entries per column.

## 3. `schema_inference.json` (stage 1 AI step A)

```json
{
  "schema_version": "1.0",
  "generated_at": "...",
  "model_used": "claude-sonnet-5",
  "domain_confidence": 0.93,
  "domain_reasoning": "columns resemble product / date / quantity / price",
  "dataset_issues": [
    {"code": "duplicate_rows", "count": 12, "severity": "medium",
     "detail": "12 exact duplicate rows"}
  ],
  "columns": [
    {
      "source_name": "Prod Name",
      "semantic_type": "text",
      "canonical_field": "product_name",
      "confidence": 0.95,
      "issues": [
        {"code": "missing_values", "count": 142, "pct": 3.1,
         "examples": ["row 88", "row 105"]}
      ]
    }
  ]
}
```
Enums: see `docs/AI_PIPELINE.md` section 5. Validation rules: every profiled
column appears exactly once; at most one column per canonical field except
`ignore`; confidence in [0,1]. An issue's `pct` is a number in [0,100] or
`null` when the profile holds no percentage for that issue (the AI never
invents one); the key is always present.

## 4. `plan_proposed.json` and `plan_final.json` (stage 1 steps C and D)

Identical schema; `plan_final.json` additionally records user edits.

```json
{
  "schema_version": "1.0",
  "generated_at": "...",
  "source": "ai" | "user_edited" | "manual",
  "dataset_actions": [
    {"action": "remove_exact_duplicates", "params": {},
     "rationale": "12 exact duplicate rows found",
     "alternatives": ["flag_only"], "edited_by_user": false}
  ],
  "column_actions": [
    {"source_name": "Unit Price", "semantic_type": "numeric_continuous",
     "canonical_field": "unit_price", "action": "impute_median", "params": {},
     "rationale": "4.2% missing; median robust given IQR outliers",
     "alternatives": ["impute_mean", "drop_rows_missing"],
     "edited_by_user": true}
  ]
}
```
`plan_final.json` is what stage 1 executes. The backend validates it against the
transform catalog and the legality matrix before execution; an invalid plan is
rejected whole (never partially applied).

## 5. `cleaning_report.json` (stage 1 output F)

```json
{
  "schema_version": "1.0", "generated_at": "...",
  "rows_in": 152430, "rows_out": 151988,
  "columns_in": 9, "columns_out": 8,
  "changes": [
    {"action": "impute_median", "column": "Unit Price", "cells_affected": 6402,
     "rows_affected": 0, "params": {}, "detail": "filled with 8.5"},
    {"action": "drop_rows_missing", "column": "transaction_date",
     "cells_affected": 0, "rows_affected": 430, "params": {},
     "detail": "dropped rows with unparseable dates"}
  ],
  "warnings": [
    {"code": "encoding_fallback", "detail": "file decoded as latin-1"}
  ],
  "column_mapping": {"Prod Name": "product_name", "Qty": "quantity"}
}
```

## 6. `metrics.json` (stage 2 output)

```json
{
  "schema_version": "1.0", "generated_at": "...",
  "period": {"current": "2011-11", "previous": "2011-10",
             "data_start": "2010-12-01", "data_end": "2011-12-09"},
  "core": {
    "revenue_current": 1150000.0, "revenue_previous": 1290000.0,
    "revenue_change_pct": -10.9,
    "orders_current": 1820, "orders_previous": 1950,
    "active_customers_current": 812, "active_customers_previous": 905,
    "aov_current": 631.9, "aov_previous": 661.5,
    "return_rate_current": 0.042, "return_rate_previous": 0.038,
    "revenue_by_month": [{"period": "2011-01", "revenue": 690000.0}]
  },
  "customers": {
    "rfm_reference_date": "2011-12-10",
    "segments": [
      {"segment": "Champions", "customers": 118, "revenue_share_pct": 34.2,
       "avg_monetary": 3320.5, "customers_previous": 129}
    ],
    "new_vs_returning": {"new_customers": 74, "returning_customers": 738,
                         "new_revenue": 92000.0, "returning_revenue": 1058000.0}
  },
  "products": {
    "pareto": {"products_for_80pct_revenue": 63, "total_products": 412,
               "concentration_pct": 15.3},
    "top_products": [{"product": "WHITE HANGING HEART T-LIGHT HOLDER",
                      "revenue": 38400.0, "units": 5120}],
    "biggest_decliners": [{"product": "...", "revenue_change_pct": -41.2}],
    "velocity": [{"product": "...", "units_per_day": 12.4,
                  "days_to_stockout": 8.6}]
  },
  "by_dimension": {
    "country": [{"name": "United Kingdom", "revenue_current": 940000.0,
                 "revenue_previous": 1020000.0, "contribution_pct": 57.1}],
    "category": [{"name": "Home Decor", "revenue_current": 210000.0,
                  "revenue_previous": 268000.0, "contribution_pct": 41.4}]
  }
}
```
`contribution_pct` = share of the total change attributable to that dimension
member (signed), not share of revenue. Stage 2 never calls the AI.

## 7. `diagnosis.json` (stage 3 output)

```json
{
  "schema_version": "1.0", "generated_at": "...", "model_used": "claude-sonnet-5",
  "decomposition": {
    "metric": "revenue", "change_abs": -140000.0, "change_pct": -10.9,
    "factors": [
      {"factor": "active_customers", "contribution_abs": -102300.0,
       "contribution_pct": 73.1, "value_current": 812, "value_previous": 905},
      {"factor": "purchase_frequency", "contribution_abs": -21400.0,
       "contribution_pct": 15.3, "value_current": 2.24, "value_previous": 2.15},
      {"factor": "aov", "contribution_abs": -16300.0, "contribution_pct": 11.6,
       "value_current": 631.9, "value_previous": 661.5}
    ],
    "method": "multiplicative decomposition, sequential substitution"
  },
  "ai_findings": {
    "headline": "Revenue fell 10.9% driven mainly by customer count",
    "root_cause": {
      "driver": "loss of 93 active customers, concentrated in the At-risk segment",
      "evidence": "active_customers 905 -> 812; At-risk segment grew 129 -> 168",
      "secondary": ["AOV down 4.5% in Home Decor"]
    },
    "ruled_out": [
      {"hypothesis": "price increases drove customers away",
       "evidence_against": "median unit_price unchanged at 8.5"}
    ]
  }
}
```
The AI receives `metrics.json` + the computed `decomposition` block only. It never
computes the decomposition itself.

When the AI step is unavailable, meaning no AI output was accepted after the
shared retry (`docs/AI_PIPELINE.md` section 9), stage 3 still writes this file:
`decomposition` is always filled, and `model_used` and `ai_findings` are both
`null`. They are either both `null` or both filled, never partially filled. The
keys are always written: `null` is a value, not a missing key. Minimum counts
such as "at least two `ruled_out`" (`docs/AI_PIPELINE.md` section 7) are
enforced by stage 3 before writing, not by this contract.

## 8. `forecast.json` (stage 4 output)

```json
{
  "schema_version": "1.0", "generated_at": "...", "model_used": "claude-sonnet-5",
  "forecast": {
    "method": "weighted moving average with monthly seasonality index",
    "horizon_periods": 3,
    "revenue": [
      {"period": "2011-12", "point": 1210000.0, "low": 1040000.0,
       "high": 1380000.0, "confidence": 0.8}
    ],
    "insufficient_history": false,
    "products_at_stockout_risk": [
      {"product": "...", "days_to_stockout": 8.6, "suggested_reorder_units": 420}
    ]
  },
  "recommendations": [
    {
      "priority": 1,
      "insight": "At-risk segment grew from 129 to 168 customers",
      "cause": "customer count is 73.1% of the revenue decline",
      "action": "win-back email to the 168 At-risk customers with a 14-day offer",
      "expected_impact": "168 x avg_monetary 890 x 15% reactivation = ~22,400",
      "how_to_measure": "reactivation rate and revenue from that cohort, 30 days",
      "confidence": 0.7
    }
  ],
  "do_not_do": [
    {"tempting_action": "discount to Champions",
     "why_wrong_here": "Champions revenue share is stable at 34.2%"}
  ]
}
```
Forecast numbers come from code; the AI writes only `recommendations` and
`do_not_do`, and every `expected_impact` must show its arithmetic from input
numbers.

When the AI step is unavailable, meaning no AI output was accepted after the
shared retry (`docs/AI_PIPELINE.md` section 9), stage 4 still writes this file:
`forecast` is always filled, and `model_used`, `recommendations` and
`do_not_do` are all `null`. They are either all `null` or all filled, never
partially filled. The keys are always written: `null` is a value, not a missing
key, and it is never replaced by an empty list. Minimum counts such as "3 to 5
recommendations" (`docs/AI_PIPELINE.md` section 8) are enforced by stage 4
before writing, not by this contract.

## 9. `report.json` (stage 5 output, data layer)

```json
{
  "schema_version": "1.0", "generated_at": "...",
  "run_id": "...", "source_file": "sales_2011.csv",
  "data_quality": {"rows_in": 152430, "rows_out": 151988,
                   "issues_fixed": 7, "warnings": 1},
  "layer_1_numbers": { "...": "selected fields from metrics.json" },
  "layer_2_causes": { "...": "selected fields from diagnosis.json" },
  "layer_3_actions": { "...": "recommendations from forecast.json" },
  "charts": [
    {"id": "revenue_trend", "type": "line", "title": "Revenue by month",
     "series": [{"name": "revenue", "x": ["2011-01"], "y": [690000.0]}]}
  ],
  "provenance": {"stages_run": ["ingest", "analyze", "diagnose", "predict"],
                 "ai_calls": 4, "models_used": ["claude-sonnet-5"]}
}
```
Stage 5 performs no analysis: it selects, orders and formats. Any number in
`report.json` must be traceable to an earlier contract file - this is what makes
the report defensible.

## 10. Versioning and change policy

- Adding an optional field: minor bump (`1.0` -> `1.1`), readers unaffected.
- Renaming/removing a field or changing its meaning: major bump, update the
  Pydantic model, update every consumer stage in the SAME session, and record
  the change in `PROJECT_PLAN.md` section 12 Notes.
- Never let a stage read a field that is not documented here. If a stage needs
  new data, add it to the contract first, then implement.
- 2026-09-19: the nullable AI blocks in sections 7 and 8 were added in place at
  `1.0`, without a bump, because no stage and no contract file existed yet
  (Phase 0B). From the first contract file a stage writes onward, every
  change follows the rules above.
- 2026-09-19: section 3's issue `pct` became nullable in place at `1.0` (1C),
  because no `schema_inference.json` had been written yet; the prompt already
  allowed `null`, and the AI must not invent a percentage.
