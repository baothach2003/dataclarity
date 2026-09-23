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
invents one); the key is always present. An issue's `count` is never the AI's
estimate: it comes from `profile.json` (`missing_values`, `all_null_column`,
`duplicate_rows`) or is computed by pandas from the raw file, and an issue whose
count is 0 is left out (`docs/AI_PIPELINE.md` section 11).

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
     "alternatives": [], "edited_by_user": false}
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

Every source column appears exactly once in `column_actions`. `alternatives`
lists at most 2 other actions, each legal for that column, with no repeats and
never the chosen action. For a dataset action they are dataset-scope actions
(`remove_exact_duplicates`, `flag_duplicate_keys`) or empty: `flag_only` needs a
column, so it is not one (this example used to list it). `semantic_type` and
`canonical_field` are those of `schema_inference.json` in `plan_proposed.json`; in
`plan_final.json` they are the user's, who may have changed either. Columns beyond
the 25 the AI sees get `flag_only` with a note that they were not analyzed.
`plan_final.json` is written by the execution together with `cleaned.csv` and
`cleaning_report.json` (section 5), and is the plan exactly as it ran.

## 5. `cleaning_report.json` (stage 1 output F)

```json
{
  "schema_version": "1.0", "generated_at": "...",
  "rows_in": 152430, "rows_out": 151988,
  "columns_in": 9, "columns_out": 8,
  "changes": [
    {"action": "impute_median", "column": "Unit Price", "cells_affected": 6402,
     "rows_affected": 0, "params": {}, "detail": "filled with 8.5"},
    {"action": "drop_rows_missing", "column": "Prod Name",
     "cells_affected": 0, "rows_affected": 430, "params": {},
     "detail": "dropped 430 rows with no Prod Name"}
  ],
  "warnings": [
    {"code": "encoding_fallback", "detail": "file decoded as latin-1"}
  ],
  "column_mapping": {"Prod Name": "product_name", "Qty": "quantity"}
}
```

Rules for the values (no field changed):
- `changes` holds every action of the plan, in the order it ran (the fixed order of
  `docs/AI_PIPELINE.md` section 6), one entry each even when it changed nothing.
- `rows_in` and `columns_in` describe `raw.csv`; `rows_out` and `columns_out`
  describe `cleaned.csv`, so `columns_out` also counts the `__flag_*` columns the run
  added.
- `column_mapping` lists the columns that are in `cleaned.csv` and mapped to a
  canonical field other than `ignore`: an ignored or dropped column is not there.
- `encoding_fallback` is warned, with the detail "file decoded as latin-1", when the
  file was not UTF-8. `cleaned.csv` is always UTF-8. `text_reads_as_missing` is warned,
  with the count and the columns, when cells hold text that reads back as missing
  once the file is read again (an empty text, NA, N/A, NULL...).
- A flag column that would be all False is not in `cleaned.csv`, and a flag never
  overwrites a source column of the same name (it takes `_2`, `_3`...).
- `cleaned.csv` keeps the source column names, writes dates as ISO 8601 and holds the
  flag columns (`__flag_<kind>__<column>`, `__flag_duplicate_key`).

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

**Rows with a blank category are excluded from `by_dimension`**, because this
block answers "revenue by category" and an unnamed category is not one; their
revenue still counts in `core`. Section 7's `localization` **includes** them
as a visible `(uncategorised)` member, because that block answers "where did
the change happen" and has to account for the whole change. The divergence is
deliberate, the two blocks have different jobs, and **neither should be
changed to match the other** - see the note in section 7.

## 7. `diagnosis.json` (stage 3 output)

Produced by the 8-step diagnostic engine in `docs/AI_PIPELINE.md` section 7.
Steps 1-7 are deterministic pandas and fill every block below except
`ai_findings`; step 8 is the only AI call and writes only `ai_findings`. Why
the attribution is Shapley and why the hypothesis catalog is fixed in advance:
`docs/adr/0004-shapley-attribution.md` and
`docs/adr/0005-pre-registered-hypothesis-catalog.md`. Why a `level`-mode
signal describes rather than decides, and what stage 5 must therefore not say
about one: `docs/adr/0006-level-signals-are-descriptive.md`.

```json
{
  "schema_version": "1.0", "generated_at": "...", "model_used": "claude-sonnet-5",
  "frame": {"current": "2011-11", "previous": "2011-10",
            "year_ago_current": "2010-11", "year_ago_previous": "2010-10",
            "history_months": 23, "history_start": "2009-12", "history_end": "2011-10"},
  "trust": {
    "verdict": "caution",
    "checks": [{"id": "D1", "status": "caution",
                "evidence": {"zero_days_cur": 6, "excess_zero_days": 5.2,
                             "estimated_revenue_gap": 18400.0},
                "message": "6 days of the current month have no rows at all"}],
    "limitations": ["rows dropped in stage 1 cannot be assigned to a period"]
  },
  "calendar": {"method": "weekday_weights", "expected_cur": 1180000.0,
               "expected_prev": 1210000.0, "calendar_effect": -31900.0,
               "calendar_adjusted_change": -108100.0,
               "evidence": {"weights": {"mon": 31200.0, "sat": 52100.0}}},
  "signals": [{"series": "revenue", "mode": "level", "value_cur": 1150000.0,
               "center": 1240000.0, "lower": 1090000.0, "upper": 1390000.0,
               "signal": "within", "rule": null}],
  "tree": {
    "method": "shapley",
    "lever": {
      "level1": {"formula": "customers*frequency*aov",
                 "factors": [{"name": "customers", "value_prev": 905.0,
                              "value_cur": 812.0, "contribution": -102300.0}]},
      "level2": {"formula": "units_per_order*price_per_unit",
                 "factors": [{"name": "units_per_order", "value_prev": 4.1,
                              "value_cur": 3.9, "contribution": -11200.0}]},
      "gross_to_net": 1.04, "masked_shift_alert": false, "reasons": {}
    },
    "customers": {"new": 92000.0, "resurrected": 14000.0, "expansion": 61000.0,
                  "contraction": -88000.0, "lapsed": -219000.0,
                  "unattributed": 0.0, "previous_transition": {},
                  "evidence": {"new_customers": 148, "left_censored": false,
                               "new_customers_whose_first_activity_is_a_return": 3,
                               "empty_period": []}},
    "returns": {"gross_prev": 1338000.0, "gross_cur": 1198000.0,
                "returns_prev": 48000.0, "returns_cur": 48000.0},
    "products": {"volume": -96000.0, "mix": -21000.0, "price": -8000.0,
                 "new_products": 12000.0, "discontinued_products": -27000.0}
  },
  "localization": {
    "dimensions": [{"name": "category",
                    "members": [{"name": "Home Decor", "rev_prev": 268000.0,
                                 "rev_cur": 210000.0, "delta": -58000.0,
                                 "share_of_change": 0.414, "is_data_gap": false}],
                    "other": {"name": "Other", "rev_prev": 31000.0, "rev_cur": 29500.0,
                              "delta": -1500.0, "share_of_change": 0.011,
                              "is_data_gap": false},
                    "new_members": [], "removed_members": [],
                    "size_filter_waived": false, "member_count": 14}],
    "mix_rate": {"metric": "aov", "mix": -24450.0, "rate": 3050.0},
    "breadth": {"declining_base_share": 0.74, "top_member_share": 0.41,
                "classification": "broad"}
  },
  "hypotheses": [{"id": "P2", "family": "price_mix", "lens": "product",
                  "statement": "Sales mix shifted towards cheaper products",
                  "verdict": "supported", "contribution": -21000.0, "share": 0.21,
                  "evidence": {"mix_effect": -21000.0, "delta_gross": -100000.0},
                  "rule": "same sign and share >= 0.20"}],
  "not_testable": [{"id": "X1", "statement": "Marketing, promotions, discounts",
                    "reason": "no campaign data; discount columns are not canonical"}],
  "headline": {"rule": 6, "hypothesis_id": "P2", "lens": "product",
               "message": "Most of the decline is consistent with a shift in sales mix towards cheaper products."},
  "ai_findings": {
    "summary": "Revenue fell 10.9% this month...",
    "headline_explanation": "The mix effect accounts for 21% of the drop...",
    "hypothesis_notes": [{"id": "P2", "text": "Shoppers bought more of the cheaper lines..."}],
    "not_tested_note": "This data cannot test marketing, competitors, weather or footfall."
  }
}
```

**Types.** `frame.current`/`previous`/`year_ago_*`/`history_start`/`history_end`
are `YYYY-MM` strings; `year_ago_current` and `year_ago_previous` are `null`
together when the year-ago pair is not in the data. `history_months` is a
non-negative integer. `trust.verdict` is `trusted | caution | blocked`; each
check's `status` is `ok | caution | blocked | inconclusive` and its `id` is
`D1 | D2 | D3`. `signals[].series` is one of `revenue`, `orders`,
`active_customers`, `frequency`, `aov`, `units_per_order`, `price_per_unit`,
`return_rate`; `mode` is `level | yoy`; `signal` is
`above | below | within | insufficient_history`; `rule` is `1 | 2 | null`
(`null` when no rule fired or the series has insufficient history), and
`center`/`lower`/`upper`/`value_cur` are `null` under `insufficient_history`.
`signals[].limits_method` is `median_moving_range | mean_moving_range |
minimum_spread`, naming what actually drew the limits - `minimum_spread` means
neither estimator measured any variation and a floor in the series' own units
was used, which a reader must be able to tell apart from a measured chart.
**`mode` is decided per series, so one run's signals mix units**: `value_cur`,
`center`, `lower` and `upper` are money or counts on a `level` row and
percentage points on a `yoy` row. Read `mode` before comparing two signals or
presenting them together.

`signals[].mode_fallback` is `no_year_ago_value | unusable_year_ago_base |
null` and `signals[].insufficient_reason` is `too_few_points |
no_current_value | no_measurable_spread | null`.
**These two must not be merged.** They answer different questions and a later
session tidying them into one field would lose a distinction step 7 depends
on:

- `mode_fallback` says the series **is charted**, on a level chart, because
  its CURRENT month's year-ago comparator was unusable.
  `unusable_year_ago_base` covers every reason the base guard in AI_PIPELINE
  7.5 refuses that comparator: not positive, floating-point residue, or -
  since 3D6 - below `YOY_MIN_BASE_SHARE` of the series' typical magnitude,
  i.e. too small to divide by. A series pushed to level mode because refused
  BASELINE bases left too few points carries `null`, as it has since 3D4 (a
  labelling gap scheduled with 3D7). Such a series still has limits and can
  still fire rule 1. It does NOT decide whether a row is a verdict -
  `is_verdict` does, and in v1 no row is (ADR-0007). This flag records why a
  series is in level mode, which 3F narrates; it is not a gate.
- `insufficient_reason` says the series has **no chart at all**, and is only
  ever set alongside `signal = "insufficient_history"`, where `center`,
  `lower`, `upper` and `value_cur` are all `null`.

`no_measurable_spread` means the baseline has its points but no variation and
no scale to borrow a floor from; it is NOT `too_few_points`, and a reader
should not go looking for more history.

### No step-4 row is a verdict in v1 (ADR-0006, ADR-0007)

**In v1 every `signals` row is descriptive, in either mode**
(`docs/adr/0007-no-step4-verdicts-in-v1.md`). ADR-0006 made `level` rows
descriptive; ADR-0007 extended that to `yoy` rows, because a year-over-year
point compares with one year-ago month that cannot vouch for itself on a
24-month file, and the chart's mean centre is dragged by one anomalous
point. What follows was written for ADR-0006 and still holds for `level`
rows; read "a `yoy` row is a judgement" as the Backlog's "unusualness
verdicts", not as v1.

**`mode` decides what a row is allowed to mean, not just its units.** A
`yoy` row is a judgement about the month. A `level` row is a description of
where the month sat on a chart whose centre is the average of every month -
which is the wrong place for any month with a season, in both directions: a
December that halves still lands above that centre, and an ordinary December
fires `above` for being ordinary.

Consumers must therefore honour the following, and
`contracts.diagnosis.is_verdict` is the single definition of "verdict":

- **T3 is `inconclusive` on every file in v1** (ADR-0007): with no row a
  verdict, nothing can establish that the change was routine. Its evidence
  lists every series that had no verdict - in v1, all of them.
- **The masked-shift alert reads no step-4 row** (ADR-0007). It rests on the
  tree - see `tree.lever` below - and `masked_shift_basis` is gone.
- **Stage 5 must never render a step-4 row as a judgement, in either mode or
  either direction.** Not `within` as "within normal variation", and not `above` or
  `below` as "unusually high" or "unusually low". The failure is symmetric:
  on a seasonal shop a December that halves reads `above` against an
  off-season centre, and so does an ordinary December - identical signal,
  identical limits. Level rows are rendered with wording that describes the
  chart without claiming the month was judged. This is a rule, not a
  preference: the step-4 gate that used to prevent such a claim was deleted
  by ADR-0006 and this is where the responsibility moved.
`calendar.method` is `weekday_weights | day_count`. `tree.method` is always
`"shapley"`.

**Arrays in the example above show one representative element.** Every
`lever` level carries exactly the factors its `formula` names, in that order -
three for `customers*frequency*aov`, two for the others - and this is enforced
by the model, not merely documented.

`tree.lever.level1` is `null` when a factor cannot be formed at all, which
happens when either period has zero orders (AOV is then 0/0). Zero *identified
customers* with orders present is not that case: it takes the two-factor
`orders*aov` form instead. `tree.lever.gross_to_net` is `null` when level 1 is
absent, and also when revenue did not move, since the ratio divides by that
change - infinity is not representable in JSON. `tree.lever.masked_shift_alert`
is `null` **whenever level 1 is `null`, and is never `false` in that case**:
`false` asserts that the check ran and found nothing, and a reader must not
take "the tree could not be built" for "no masked shift". Since ADR-0007 it is
also `null` when the history window holds no complete trading month, because
the alert measures "material" against the typical month and there is none.
It is decided on the tree alone: against a floor of
`MASKED_MIN_CONTRIBUTION_SHARE` times the largest of the typical month, the
previous month and the current month, one contribution of each sign on
`tree.lever.masked_shift_pair` clears it, the revenue change stays under the
same share of the larger compared month, and `gross_to_net` reaches
`MASKED_GROSS_TO_NET` (AI_PIPELINE 7.6). `masked_shift_pair` is level 1 re-split as
`orders*aov` - the pair the alert is decided on and headline rule 4 names -
because customers x frequency = orders by definition and those two cancel
exactly whenever orders hold steady. It is `null` exactly when level 1 is,
is always `orders*aov`, is built from the period's own order count and
revenue, and must match level 1 - the same orders and AOV in both periods,
and contributions summing to the same revenue change. An alert that fired
must carry it. Files written before 3D6b have no such field and still load,
unless they carry a fired alert; no stage has written a `diagnosis.json`
yet, so none does.
It is also `null`, with a reason, when either compared month netted zero or
below: the multiplicative split then changes sign and cannot be read.
3F and headline rule 4 always phrase it as possibly seasonal. Every null field
in `lever` carries an entry in `tree.lever.reasons`, keyed by field name; a
null `masked_shift_alert` needs its own entry only when level 1 is present,
since beside a null level 1 it is explained by level 1's reason.
`masked_shift_basis` was removed by ADR-0007; a file still carrying it is read
and the field ignored.

`localization.dimensions[].name` is `category | product | customer_type`;
`category` is absent when no column is mapped to it. Each member carries
`is_data_gap`, true for the bucket holding rows whose key column was blank -
`(uncategorised)`, `(no product name)`, `(no customer)`. Those buckets exist so
the dimension still accounts for its whole change, and step 7 must never write
a recommendation about one as though it were a real product group. **A member
is identified by that flag, not by its name**: a real category spelled
`(uncategorised)` stays a separate member. Data-gap buckets never appear in
`new_members` or `removed_members`, which carry bare strings with no flag and
would otherwise announce "a new category launched this month: (uncategorised)".

`size_filter_waived` is true when **no** member cleared the size bar and the
top movers were named anyway, so that step 7 can tell a `concentrated` verdict
over genuinely large members from one over members that are all small. It is
not set merely because a dimension small enough to fit in the named slots
skipped the filter. `member_count` is how many members the dimension had
before ranking and grouping: five named out of seven is a different story from
five out of five hundred.

`localization.breadth` is measured over the **product** dimension, the finest
and the only one always present, and over *every* member rather than the named
few - measured over the top five, every change would look concentrated, since
the top five are chosen for being the largest movers.

**Blank categories are handled differently here from `metrics.json`'s
`by_dimension` (section 6), on purpose. Do not "fix" either one to match the
other.** Section 6 answers "revenue by category" and excludes rows with no
category, because an unnamed category is not a category. Section 7 answers
"where did the change happen" and must account for the *whole* change, so it
keeps those rows as a visible `(uncategorised)` member; dropping them would
leave the dimension reconciling to a subtotal while the rest of the report
talks about the full figure - which is exactly the defect session 3C found in
the product lens. The two blocks have different jobs, and only one of them
carries a reconciliation duty.

`tree.customers.evidence` is a free-form object carrying what C1 and C3 need
before trusting the `new` term: `left_censored` (whether `cur` falls in the
file's first `LEFT_CENSOR_MONTHS` months), `empty_period` (which side of the
transition, if either, holds no rows at all), and
`new_customers_whose_first_activity_is_a_return` - customers classified as new
whose earliest row in the whole file is a refund, which usually means their
purchase predates the file. That count is evidence only and changes no term;
excluding those customers would break the bridge identity. It also carries
`customer_values_merged_by_normalisation`: how many distinct raw customer
values the shared `customer_identity` key collapsed across the whole file
(distinct raw values minus distinct identities, so a customer written three
ways contributes 2). A large number says the customer column is inconsistently
entered, which is context for every C-family verdict built on it. `hypotheses[].verdict` is
`supported | partial | ruled_out | inconclusive | not_testable`; `contribution`
and `share` are `null` for directional hypotheses (D2, D3, T3, C4, R1), which
carry their test in `evidence` and `rule` instead. `headline.rule` is `1`-`7`
(`docs/AI_PIPELINE.md` section 7); `hypothesis_id` and `lens` are `null` for
rules that name no hypothesis (1, 2, 3, 4, 5, 7). Every `evidence` value is a
free-form JSON object of serialisable scalars and lists, like `params` in
section 4. All money and share figures are floats; counts are integers.
`ai_findings` (when present) is `{summary, headline_explanation,
hypothesis_notes: [{id, text}], not_tested_note}`, all strings;
`hypothesis_notes` carries one entry per `supported` or `partial` hypothesis
and every `id` in it must exist in `hypotheses` (enforced by the step 8
validator, `docs/AI_PIPELINE.md` section 7.9, not by this schema).

**Rules.**
- `headline.message` is written by code, never by the AI: the report must still
  state its conclusion when the AI is unavailable. The AI explains that
  sentence in `ai_findings`, it does not replace it.
- `hypotheses` always contains every id in the fixed catalog
  (`docs/AI_PIPELINE.md` section 7), in catalog order, including the ones that
  came out `ruled_out` or `not_testable` for this run. A cause is never absent
  because it failed - showing what was tested and rejected is the point
  (`docs/adr/0005-pre-registered-hypothesis-catalog.md`).
- `not_testable` lists the X-family causes that DataClarity's schema cannot
  reach at all. It is constant per run, not data-dependent.
- Lenses never sum together. The lever and customer lenses each reconcile to
  `delta_net`, the product lens to `delta_gross`, the returns lens to
  `delta_net`. A reader must not add shares across lenses, and stage 5 must not
  present them as one total.
- `tree.customers` is `null` when no column is mapped to `customer`, and
  `tree.lever.level1.formula` is then `"orders*aov"`. `tree.lever.level2` is
  `null` when net units are not positive in both periods (inconclusive).
  `localization.mix_rate` is `null` when no category column is mapped.
- When `trust.verdict` is `blocked`, `calendar`, `signals`, `tree` and
  `localization` are all `null`, every hypothesis outside the D family is
  `inconclusive`, and `headline.rule` is `1`.
- Stage 2 also reports stockout risk (`metrics.json` `products.velocity`,
  section 6), by a different method: an inventory balance projected forward
  from net in-minus-out. Hypothesis R3 here is a *sales-gap* signal - a product
  that sold on most days and then stopped while the store kept trading. The two
  can legitimately disagree about the same product, and stage 5 must label
  which is which rather than merge them.

When the AI step is unavailable, meaning no AI output was accepted after the
shared retry (`docs/AI_PIPELINE.md` section 9), stage 3 still writes this file:
every deterministic block is filled as usual, and `model_used` and
`ai_findings` are both `null`. They are either both `null` or both filled,
never partially filled. The keys are always written: `null` is a value, not a
missing key. Stage 3 never fails because of the AI.

The AI receives the complete deterministic output of steps 1-7 as JSON, never
raw rows, and may not choose, add, remove or re-rank hypotheses, nor upgrade a
verdict (`docs/AI_PIPELINE.md` section 7, step 8).

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
- 2026-09-21: section 3 says where an issue's `count` comes from and that a count
  of 0 is omitted, and section 4 now states the rules for `alternatives` and
  corrects the dataset-action example (1E). No field was added, renamed or
  changed, so `schema_version` stays `1.0`: these are rules the stage enforces on
  values the schema already allowed.
- 2026-09-21: section 5 states how the values are built and section 4 that
  `plan_final.json` is written by the execution and carries the user's types and
  mapping (1F). No field was added, renamed or changed, so `schema_version` stays
  `1.0`.
- 2026-09-21: section 5 gains the `text_reads_as_missing` warning and two rules for
  the flag columns, and its example no longer shows an entry the stage cannot
  produce (`drop_rows_missing` acts on a source column and drops missing cells, not
  unparseable dates) (1F review). No field changed; `schema_version` stays `1.0`.
- 2026-09-22: section 7 was **replaced in place at `1.0`** (Stage 3 SPECS UPDATE
  session, from `docs/DIAGNOSE_DESIGN.md`). The single `decomposition` block
  became the eight blocks of the diagnostic engine (`frame`, `trust`,
  `calendar`, `signals`, `tree`, `localization`, `hypotheses`, `not_testable`,
  `headline`), and `ai_findings` changed from the AI choosing hypotheses to the
  AI narrating hypotheses code already decided. This is a breaking rewrite, not
  an addition, and it is done without a major bump under the same precedent as
  the 2026-09-19 entries above: no `diagnosis.json` has ever been written, no
  stage reads it yet, and `contracts/diagnosis.py` has no data to migrate.
  **Until session 3 of Phase 3 rewrites `contracts/diagnosis.py`, this section
  and that Pydantic model deliberately disagree** - the model (and
  `tests/contracts/test_diagnosis.py`) still describe the old shape. That is a
  known, time-boxed divergence recorded here because CLAUDE.md section 1
  requires doc/code conflicts to be reconciled rather than left silent; the
  session that rewrites the model closes it. `run_id` from
  `DIAGNOSE_DESIGN.md` section 6's skeleton was deliberately left out: no other
  stage output carries it (the run id is the directory name), only
  `report.json` does, because that file is downloaded standalone. Adding it
  later is a minor bump under the first rule above.
- 2026-09-23: **the divergence recorded in the entry above is closed.** Session
  3C rewrote `contracts/diagnosis.py` and `tests/contracts/test_diagnosis.py`
  against this section; the model and the doc describe the same file again.
  Two fields were added to section 7 in the same session, in place at `1.0`
  under the same precedent (no `diagnosis.json` has been written yet):
  `tree.lever.reasons`, because a null field that does not say why it is null
  cannot be acted on downstream, and `tree.customers.evidence`, which carries
  the left-censoring hints C1/C3 need. Both are documented in section 7's
  Types paragraph. The old `tests/contracts/test_diagnosis.py` pinned the
  pre-3A shape; the tests naming `decomposition`, `root_cause` and `ruled_out`
  could not survive a block that no longer exists, and every rule that still
  applies - the all-or-nothing AI blocks, a dropped key not parsing as a
  degraded run - is still tested, unchanged in substance.
- 2026-09-23 (session 3D6b, ADR-0007): `tree.lever.masked_shift_basis`
  **removed**, and `tree.lever.masked_shift_alert` may now be `null` with
  level 1 present (no typical month to measure against), always with a
  reason. Done in place at `1.0` under the precedent above - no
  `diagnosis.json` has been written by any stage yet - and a file written
  before the change still loads: the retired field is ignored (contract models
  ignore unknown fields), and a null alert beside a null level 1 needs no
  reason of its own. Both are pinned by tests; the first version of the
  validator broke the second, found by the 3D6b doubt-review. Same session:
  `tree.lever.masked_shift_pair` **added** (optional, `orders*aov`), the
  split the alert is decided on.
