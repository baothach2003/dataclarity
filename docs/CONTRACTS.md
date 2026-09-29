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
  write. Re-running a stage overwrites only its own outputs. When a stage
  runs again, the backend removes every LATER stage's output (3G-lite): a
  diagnosis of metrics a re-analysis replaced would keep its headline about
  another month. They are set aside around the new output's rename,
  deleted once it succeeds and put back if anything fails - all or nothing
  (3G-lite, DEMO review). So which files a run holds says how far it went.
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

`date_order` (`1.1`, session 2E-j, Thach) is present on a text column whose
day-month-year or month-day-year dates - two numbers of one or two digits and
a year of two or four, separated by `/`, `.`, `-` or spaces, anywhere in the
cell ("05/01/2026", "Mon 5.1.26 10:30"), never inside ISO or a time, and never
in a cell that also holds a year-first date ("2026-01-05 10.30.00") or a month
in words ("05-JAN-26 10.30.00 AM": its date is in words) - can be read two
ways; `null` otherwise (and absent from a `1.0` file). A four-digit year
wins among a cell's candidates; a dotted one ("10.30.00") loses to any other,
is refused before AM/PM, and two dotted ones with nothing better are no date
(2E-o). Read in an order, the date is rewritten in place, and a dotted time
in the rest of the cell is written with colons:

```json
"date_order": {"shaped": 9120, "day_first": 3940, "month_first": 0,
               "ambiguous": 5010, "day_first_example": "13/01/2026",
               "month_first_example": null, "decision": "day_first", "hint": null}
```

A first number 13-31 with a second 1-12 proves day first, the reverse month
first (`day_first` and `month_first` count those cells, each with its first
example - the date text alone, never the rest of the cell). `ambiguous`
counts the cells either order reads, each as another date (two numbers 1-12
that differ; "05/05/2026" reads the same either way). `decision` is the
proven order, or `"ask"` when both are proven, or neither is and some cell is
ambiguous; a column where nothing depends on the order carries no measure.
`hint` is a suggestion only (2E-d2): when every such cell holds the date
alone, its first number 1 while the second varies - the 1st of each month
written day first, which can never prove itself - it is `"day_first"` (the
reverse: `"month_first"`); Review states both readings and chooses neither.
Measured per column, whatever the column is mapped to, so Review reads the
date column's own measure after a remap or on a manual plan. Stage 1's own
measure, for Review: the AI's copy of the profile leaves it out (its examples
are cells beyond the bounded sample).

## 3. `schema_inference.json` (stage 1 AI step A)

```json
{
  "schema_version": "2.1",
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
  ],
  "receipt_fill_lines": null,
  "customer_placeholders": [
    {"value": "Guest", "lines": 5210, "lines_pct": 22.8, "revenue_pct": 18.4,
     "why": "word"}
  ],
  "order_id_date_only": false,
  "non_product_candidates": [
    {"value": "DOT", "field": "sku", "name": "DOTCOM POSTAGE", "lines": 1446,
     "positive": 322657.48, "negative": -10.01, "suggested": "charge",
     "word": "postage"}
  ]
}
```
Enums: see `docs/AI_PIPELINE.md` section 5. Validation rules: every profiled
column appears exactly once; at most one column per canonical field except
`ignore`; confidence in [0,1]. Since 2E-e the canonical enum holds `order_id`
and the issue enum `order_id_not_one_order` (raised by stage 1 itself, never
by the AI), and schema_inference / plan / cleaning_report are `2.0`. An issue's `pct` is a number in [0,100] or
`null` when the profile holds no percentage for that issue (the AI never
invents one); the key is always present. An issue's `count` is never the AI's
estimate: it comes from `profile.json` (`missing_values`, `all_null_column`,
`duplicate_rows`) or is computed by pandas from the raw file, and an issue whose
count is 0 is left out (`docs/AI_PIPELINE.md` section 11).
`receipt_fill_lines` (`2.1`, session 2E-e2) is stage 1's own measure, never
the AI's: on the raw file and these columns' mapping, the lines with no
customer that the customer fill (section 6) would give their receipt's one
named customer - `0` when `order_id` or `customer` is not mapped, `null` when
the raw file cannot tell: no sale line parses before the plan's cleaning, or
blank ids make it count lines while the cleaning may still let the fill
happen (2E-e2 doubt-review cycle 2). The Review screen asks the user about
the fill when it is above 0 or `null` (and when the user remapped a field it
reads, so it was not measured). A `2.0` file reads as `null`.
`customer_placeholders` and `order_id_date_only` (`2.2`, session 2E-k, Thach)
are stage 1's own measures too, on the raw file and these columns' mapping.
A placeholder candidate is a customer value that may stand for walk-ins, at
any share when it reads as a placeholder - a whole placeholder word inside it
(read as the customer identity - 2E-i: "Guest Customer", "Cash Sale", "Walk-In Client",
"Khach le", "Consumidor Final", "Publico en General", "Laufkunde", "none",
"(blank)"), "customer" alone, "n.a.", no letter or digit ("-"), or a number
at or below zero ("0", "0.0", "-1") - and otherwise when it carries 10% or
more of the counted lines or of the sale revenue, or is the largest value by
lines or by sale revenue at 4 times the next one among the values not
already asked about (Thach's "unusual share"; a first placeholder must not
shield a second, 2E-k doubt-review cycle 3 F1). A word is part of another only
when a LETTER touches it, so plurals, codes and underscores match ("Walk-ins",
"GUEST01", "Walk_In"); the list also reads "Khach hang le", "Khach vang lai",
"Misc", "Non-member", "Unregistered", "Cliente final", "Barverkauf",
"Pelanggan Umum" and the Chinese default (cycle 3 F3). Since 2E-r: words
written apart may be joined by any run of spaces, underscores or hyphens
("Retail_Customer", "No-Customer", "Walk - In"), the Chinese default counts
inside a longer name ("门店散客"), "n/a" forms count ("#n/a", "n / a"), the
value is read composed (NFC), and the 4-times test is taken again after each
value it finds, so one code never shields the next.
Measured: the largest real customer is 4.4% of either demo file and 1.01-1.15
times the next one; Online Retail II's walk-ins are 22.8% of its lines, 18.5
times its largest customer. No date is read for this search. Review asks about each
(section 4). `order_id_date_only` says whether the order-id check could read
dates only (section 6). Both are `null` when not measured (the raw file did
not parse into lines, or a file older than `2.2`); Review then reads
profile.json.
`non_product_candidates` (`2.3`, session 2E-d2, Thach) is stage 1's own
measure too: the product keys whose lines may not be products - postage,
fees, commissions, bank charges, discounts, accounting adjustments. A key is
the line's SKU when it has one, else its name (`shared/line_classes.py`,
`field` says which), read as products are read. It is a candidate when its
SKU text, or the name its lines carry most often, has a class word as its
FIRST or LAST word - letter-bounded, plural "s"; in order, adjustment
(adjust, adjustment, bad debt, write-off, "dieu chinh"), pooled ("manual",
since 2E-l: Online Retail II's M is manually priced sales), discount
(discount, coupon, "giam gia", "chiet khau"), gift card (gift card, gift
voucher, gift certificate, "gift_" - since `4.0`, 2E-t1: a voucher sold is a
liability; after the discount words, so "Discount voucher" is a discount, and
no bare "voucher" or "gift"), charge (postage, shipping,
delivery, carriage, freight, p&p, "phi van chuyen", "phi ship"), cost (fee,
bank charge, commission, and "sample" since 2E-l; not the Vietnamese "hoa
hong", which is also roses) - and
its counted lines move money. Measured on Online Retail II: "carriage"
inside a name was four real products (FRENCH CARRIAGE LANTERN, BAROQUE
CARRIAGE CLOCK), so first-or-last; 13 keys are asked, among them C2
"CARRIAGE" and 23444 "Next Day Carriage", which a scan of digit-free codes
had missed - 20 since 2E-t1, with the seven gift-voucher codes that move
money (`gift_0001_10`, `_20`, `_30`, `_40`, `_50`, `_70` and `_80`; `_60` and
`_90` move none). `positive` and `negative` sum the counted lines' amounts by sign
(M "Manual": +341,104.90 and -423,886.17). `suggested` never applies by
itself. `null` when not measured (quantity or price not mapped, nothing
counted); Review then reads profile.json.

## 4. `plan_proposed.json` and `plan_final.json` (stage 1 steps C and D)

Identical schema; `plan_final.json` additionally records user edits.

```json
{
  "schema_version": "2.1",
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
  ],
  "confirmations": {"order_id_is_receipt": null,
                    "customer_on_first_line_only": null}
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

`confirmations` (`2.1`, session 2E-e2, Thach) holds the user's answers to the
Review screen's two questions (booleans or `null`, never coerced; a `null`
object reads as no answers); `null` is "not asked or not answered":
- `order_id_is_receipt`: asked when `order_id` is mapped and the order-id
  check could read dates only, judged per receipt (2E-k; section 6): most
  receipts name no customer (after the fill; a confirmed walk-in placeholder
  names none), one customer is on most of them, fewer than two different
  customers are named, or there is no customer column - a daily batch or
  Z-report code passes that check.
  Unless `true`, the figures count lines (section 6) - unconfirmed means
  untrusted. `false` counts lines whatever the customer column holds after
  cleaning (a plan that imputes it cannot silence the answer).
- `customer_on_first_line_only`: asked when the customer fill would happen
  (`receipt_fill_lines` above 0, section 3). `false` withholds the fill: a
  receipt's unnamed lines keep no customer (section 6). Unanswered, the fill
  happens, as in 2E-f: withheld by default, a header-style credit note's named
  line kept its customer while the purchase it refunds lost it, and a
  first-time buyer read as returning (2E-e2 doubt-review A).
- `customer_placeholders` (`2.2`, 2E-k): the customer values the user
  confirmed as a placeholder for walk-ins, as written (stages compare them by
  customer identity). Their lines have no customer (section 6). Sent only when
  there are some; an answer applies only to the customer column it was given
  for.
- `line_classes` (`2.3`, 2E-d2): the product keys the user classed in Review
  as not products - `{"value", "field": "sku" | "product_name",
  "line_class": "charge" | "discount" | "pooled" | "cost" | "adjustment" |
  "gift_card" | "product"}` (`pooled` and `product` since 3.0, 2E-l;
  `gift_card` since 4.0, 2E-t1 - outside revenue, the line taxonomy's
  decision 4), the value as
  written (stages compare it as they compare products; a `sku` answer does
  not class a line without a SKU - except that such a line whose name is sold
  under exactly one SKU takes that SKU's class while the name itself is
  unanswered, section 6). Unanswered, a key is not listed and its lines stay
  products. `product` is sent for a NAME the user called "a product": it is an
  answer, so those lines keep no class and do not take their SKU's (2E-l
  review cycle 1; the user is the final authority). For a SKU "a product"
  changes no figure, and since `4.0` (2E-t1) it is sent too: an answered key
  carries no pending suggestion into cleaned.csv (section 5). Sent only when there are some; an
  answer applies only to the product column it was given for. What each
  class does: section 6.
The AI's proposal never carries an answer (stage 1 builds it field by field),
and the Review screen sends only answers to questions that still apply, about
the columns they were given for - except the receipt answer: an answer
about the order id column, Yes or No, holds while that column is the order
id, asked or not (a No always counts, 2E-e2 cycle 3 F2; a Yes must not vanish
when a remap or a placeholder hides the question, 2E-k doubt-review F3). `confirmations: null` reads as
no answers in the plan and in the report alike.
The customer column is never imputed (2E-k, Thach; the transform catalog
refuses it whatever its semantic type): a filled-in value made a customer the
file never named, and read an unanswered receipt question as trusted on a
file Review judged by date only (2E-e2 doubt-review cycle 3 F1, resolved). A plan whose only change from the proposal is
its answers has `source` "user_edited". A `2.0` plan reads as nothing
confirmed.

`confirmations.dates_day_first` (`3.1`, session 2E-j, Thach) answers Review's
date question - `true`: the date column's day-month-year cells are written
day first; `false`: month first; `null`: not asked or not answered. The
user may also answer against a proven order (Thach, 2E-o Q8: one typo can
prove an order): the answer wins, and the cells only the other order can
hold become undated, counted with their reason. Asked when that column's
`date_order.decision` is `"ask"` (section 2), and then required: stage 1 refuses to execute a plan whose date column proves neither
order (or both) and carries no answer, because either default fabricates
dates (an Australian shop's days 1-12 read month first landed in January to
December). A `parse_datetime` on the date column must read those cells as
the decided order does, or the plan is refused (it would write wrong dates to
`cleaned.csv`); readings are compared on those cells, so a step that happens
to be right - per cell, pandas reads "15/01/2024" as 15 January - runs.

## 5. `cleaning_report.json` (stage 1 output F)

```json
{
  "schema_version": "2.1", "generated_at": "...",
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
  "column_mapping": {"Prod Name": "product_name", "Qty": "quantity"},
  "confirmations": {"order_id_is_receipt": null,
                    "customer_on_first_line_only": null},
  "date_order": null
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
- `confirmations` (`2.1`, 2E-e2) are the plan's answers exactly as submitted
  (section 4); stages 2 and 3 read them here, with `column_mapping`. A `2.0`
  report reads as nothing confirmed.
- `date_order` (`3.1`, 2E-j) is the order the transaction_date column's
  day-month-year cells were read in: the user's answer, else what the RAW
  file proved (decided before any action runs, so a plan dropping the rows
  that prove it keeps the proof); `null` when no cell is written so, and in a
  `3.0` report. A proof is no answer, so `confirmations` keeps the user's
  alone. Stages 2 and 3 read a date column the plan did not parse in this
  order (`CleaningReportContract.applied_confirmations`); with none recorded,
  as before 2E-j (pandas month first, a cell that cannot be swapped). A
  parse step whose format puts the year first cannot read such a date and is
  never compared with the order.
- `encoding_fallback` is warned, with the detail "file decoded as latin-1", when the
  file was not UTF-8. `cleaned.csv` is always UTF-8. `text_reads_as_missing` is warned,
  with the count and the columns, when cells hold text that reads back as missing
  once the file is read again (an empty text, NA, N/A, NULL...).
- A flag column that would be all False is not in `cleaned.csv`, and a flag never
  overwrites a source column of the same name (it takes `_2`, `_3`...).
- `cleaned.csv` keeps the source column names, writes dates as ISO 8601 and holds the
  flag columns (`__flag_<kind>__<column>`, `__flag_duplicate_key`).
- **Each line's class** (`4.0`, 2E-t1; `docs/LINE_TAXONOMY.md` section 4):
  `cleaned.csv` ends with three columns stage 1 adds after the plan -
  `line_class`, one of the closed list (`contracts.cleaning.
  CLEANED_LINE_CLASSES`: sale, pooled_sale, customer_return, pooled_return,
  allowance, pooled_allowance, discount, charge, no_money, pooled_no_money,
  gift_card_sale, gift_card_redemption, cost, adjustment, stock_in,
  unclassified, unmeasurable); `class_source`, `user` when the user's answer
  about the item decided it, `rule` otherwise; `suggested_class`, the
  line-class candidate (section 3's words, found on the cleaned file) pending
  on the line's key when nobody answered it, else a blank cell - a missing
  value, never an empty text. They are read from the file as later stages
  read it (the text cleaned.csv holds), in the date order that was applied,
  and `columns_out` counts them. A file whose quantity or unit price is not
  mapped gets none, and keeps every source name - generic cleaning, or a file
  without a price, which stages 2 and 3 cannot read (unit_price is required
  from stage 2 on).
- The one exception to keeping the source names: a source column named
  exactly `line_class`, `class_source` or `suggested_class`, and not dropped
  by the plan, is kept and written as `<name>_source` (`<name>_source_2`,
  `_3`... while any source column has that name),
  `column_mapping` follows the new name, and the warning
  `reserved_column_renamed` says which (Thach's Q24 for the line taxonomy).
  The rename happens before the plan runs, so the run's flags on that column,
  `changes[].column` and the details name it as cleaned.csv holds it;
  `plan_final.json` keeps the plan as submitted (2E-t1 review cycle 2).

## 6. `metrics.json` (stage 2 output)

```json
{
  "schema_version": "10.0", "generated_at": "...",
  "period": {"current": "2011-11", "previous": "2011-10",
             "data_start": "2010-12-01", "data_end": "2011-12-09",
             "previous_complete": true, "previous_incomplete_reason": null,
             "month_grain": false},
  "core": {
    "revenue_current": 1150000.0, "revenue_previous": 1290000.0,
    "revenue_change_pct": -10.9, "revenue_change_pct_reason": null,
    "orders_current": 1820, "orders_previous": 1950,
    "active_customers_current": 812, "active_customers_previous": 905,
    "buyers_current": 790, "buyers_previous": 884,
    "aov_current": 631.9, "aov_current_reason": null,
    "aov_previous": 661.5, "aov_previous_reason": null,
    "return_rate_current": 0.042, "return_rate_current_reason": null,
    "return_rate_previous": 0.038, "return_rate_previous_reason": null,
    "revenue_by_month": [{"period": "2011-01", "revenue": 690000.0}],
    "undated_lines": 0, "undated_lines_reason": null,
    "non_product": [
      {"line_class": "charge", "lines": 3931, "amount": 449559.47,
       "amount_current": 47935.73, "amount_previous": 26311.91,
       "reason": "3,931 lines classed in Review as charges paid by the customer stay in revenue and are in no product table"}
    ],
    "identity": {
      "current": {"gross_sales": 1460682.95, "returns": 28259.70, "discounts": 474.85,
                  "other_deductions": 0.0, "other_revenue": 47935.73, "net_revenue": 1479884.13,
                  "returns_on_suggested_keys": 0.0, "money_moved": 1539048.53},
      "previous": {"gross_sales": 1128115.16, "returns": 66602.40, "discounts": 56.08,
                   "other_deductions": 0.0, "other_revenue": 26311.91, "net_revenue": 1087768.59,
                   "returns_on_suggested_keys": 0.0, "money_moved": 1222063.91}
    },
    "outside_revenue": [
      {"line_class": "cost", "scope": "file", "sign": null, "lines": 265, "amount": -310325.44,
       "lines_without_amount": 0}
    ],
    "unclassified": {"lines": 0, "amount": 0.0, "share_of_money_moved": 0.0},
    "unmeasurable": [],
    "notes": [
      {"code": "same_day_cancellations",
       "figures": ["gross_sales", "returns", "return_rate", "orders", "aov", "customers", "products",
                   "diagnosis"],
       "text": "Returns and the return rate include same-day cancellations, which the data cannot separate: ...",
       "measures": [{"name": "returns", "scope": "current", "lines": 162, "amount": -7905.67,
                     "orders": 69, "keys": null},
                    {"name": "sales", "scope": "current", "lines": 155, "amount": 7650.40,
                     "orders": 66, "keys": null},
                    {"name": "returns_unchecked", "scope": "current", "lines": 23, "amount": -18330.44,
                     "orders": 12, "keys": null}],
       "always_on": false},
      {"code": "discounts_in_prices", "figures": ["gross_sales", "discounts"], "text": "...", "measures": []}
    ]
  },
  "customers": {
    "rfm_reference_date": "2011-12-10",
    "segments": [
      {"segment": "Champions", "customers": 118, "revenue_share_pct": 34.2,
       "avg_monetary": 3320.5, "customers_previous": 129}
    ],
    "new_vs_returning": {"new_customers": 74, "returning_customers": 738,
                         "new_revenue": 92000.0, "returning_revenue": 1058000.0},
    "customers_previous_reason": null, "revenue_share_reason": null,
    "unfilled_receipt_lines": 0, "unfilled_receipt_lines_reason": null,
    "placeholder_lines": 0, "placeholder_lines_reason": null
  },
  "products": {
    "pareto": {"products_for_80pct_revenue": 63, "total_products": 412,
               "concentration_pct": 15.3, "concentration_reason": null},
    "top_products": [{"product": "WHITE HANGING HEART T-LIGHT HOLDER",
                      "revenue": 38400.0, "units": 5120}],
    "biggest_decliners": [{"product": "...", "revenue_change": -2800.0,
                           "revenue_change_pct": -41.2,
                           "revenue_change_pct_reason": null}],
    "biggest_decliners_reason": null,
    "velocity": null,
    "velocity_reason": "stock figures are not supported in v1: ...",
    "suggested_classes": {"DOTCOM POSTAGE": "charge"}
  },
  "by_dimension": {
    "country": [{"name": "United Kingdom", "revenue_current": 940000.0,
                 "revenue_previous": 1020000.0, "contribution_pct": 57.1}],
    "category": [{"name": "Home Decor", "revenue_current": 210000.0,
                  "revenue_previous": 268000.0, "contribution_pct": 41.4}],
    "contribution_reason": null
  }
}
```

**Definitions (schema 2.0, session 2E).** They live in `shared/transactions.py`
and `shared/periods.py`, so stage 3 recomputes exactly the same figures.

- **Every date is read on the wall clock as written** (Thach, 2E-h; 1F's
  rule, `shared/dates.py`, the reader stage 1 uses): a UTC offset is dropped
  and each cell keeps its own date and time, mixed offsets included; "now",
  "today", a bare time and a year outside 1900-2100 are no dates. It holds
  whatever the cleaning plan did - read as UTC before, a +10:00 shop's
  current month, the sign of its change and its closed weekday all moved.
  Every day and month of stages 2 and 3, and stage 1's order_id check, derive
  from this one reading. **`undated_lines`** counts the lines with no
  readable date (blank, or no date) - in no month and so in no month's
  figure; one outside revenue is still in the whole file's report of such
  lines (2E-t2) - and `undated_lines_reason` says so; it is null exactly
  when the count is 0.
- **The date order** (Thach, 2E-j): a cell written day-month-year or
  month-day-year is read in the order stage 1 recorded (section 5,
  `date_order`) - only such a cell; ISO, a month name or a time is read as
  before, so "2026-01-05" is never 1 May. A cell that order cannot hold (a
  month 13) is no date. **Placeholder dates** are no date too (Thach, Q2 of
  2E-h): 1899-12-30 and 1900-01-01 (Excel's day 0 and day 1, carried by a
  time-only cell) and 1970-01-01 (a zero timestamp), at any time of day.
  Both are counted in `undated_lines`, and its reason names them. The epoch
  written on a western clock (1969-12-31) is a placeholder too.
- **A month-grain file** (Thach, Q1 of 2E-h; `period.month_grain`): every
  COUNTED line is at midnight on the 1st - or every one at midnight on the
  last day of its month, an accounting period end (Thach, 2E-o Q10) - over
  two months or more - "Mar 2024" reads as the 1st. A month holding a sale
  line counts as covered (a two-month file dated 31 January is not "30 days
  into" January). Such a file records months, not days: its line on
  the 1st (or the last day) stands for the month, so no day says whether the last month is
  over. By the elapsed-day rule below it was always dropped (the report
  compared the two months before it); now the last month holding a SALE line
  is `current` once it has ended on every clock (12 hours past its end in
  UTC - the run's clock is UTC, the dates the shop's): a report pulled
  mid-month holds a month-to-date row, which compared as a whole month read
  -36.7%, and a later stock-in row made an empty month current. One pulled
  mid-month and analysed after that month ended cannot be told apart (a known
  limit). With no customer column, the order-id check by date reads only the
  month, and its reason says so. Stage 3's day-level steps do not apply
  (section 7).
- **Lines the user classed as not products** (Thach, 2E-d2, 2E-l; plan
  `confirmations.line_classes`): a **charge** the customer paid (postage)
  stays in revenue but is no order and no return line (Thach, 2E-l: an
  invoice holding only charges is no purchase; Online Retail II 157 of 40,078
  invoices, 8 of 2,769 orders in 2011-11) and is in no product table;
  **pooled items** (many items under one code: Online Retail II's M "Manual",
  manually priced sales and their refunds) are sale and return lines in every
  figure, ranked as no product, held with the gap in stage 3 (the product
  lens's `unidentified` term, never priced like-for-like); a **discount** is a
  deduction (2E-c) whatever its signs - in revenue, no sale, no return, no
  units (a -1 @ +price discount was a return line, 2E-c2 item f); a **fee or
  cost** and an **accounting adjustment** are left out of revenue and of
  every figure as an "in" row is - no revenue, order, customer or product.
  No classed line is in a product table (top products, decliners, Pareto,
  velocity). A name-only line whose name maps to one classed SKU takes that
  SKU's class (2E-l) unless its name is answered - "a product" included
  (review cycle 1). Classing charges can change new customers: a charge is
  no purchase, so a customer whose first invoice held only postage is new at
  their first purchase instead (Q7; 3 of 25 Online Retail II months, 2011-11
  unchanged at 191). A customer present in a month only through a charge
  still counts among that month's customers, as returning - as a
  refund-only customer does (2E-c; review cycle 3, Phase 8). **`core.non_product`** lists one row per class present
  (order charge, discount, pooled, cost, adjustment, gift_card - 2E-t1: a
  confirmed gift card is left out as a fee is): its dated counted lines, their amount
  over the file and in the current and previous month, and a reason saying
  where the money went - an adjustment's amount is reported as a separate
  reconciling amount (Thach; not "the file's total minus the revenue shown",
  which fees, "in" rows and undated lines also make up - review F8). Empty
  when nothing is classed. The first-day netting keys every line as it
  would be keyed unanswered (`shared/products.netting_keys`), pooled items
  included - so classing never moves who is new by netting: keyed as no
  product, a postage refund on a customer's first day unmade a new customer
  (review F1, cycle 3 F4). The name-only-to-SKU vote (2E-f L4) reads the lines
  as if nothing were classed, and never gives a line a classed SKU: classing
  one SKU moves no other product's lines (cycle 3 F3). A
  left-out line names no receipt's other lines, as an "in" row does not
  (review F9). Measured on Online Retail II, classed as Thach decided: 2011-11
  revenue 1,461,756.25 -> 1,479,736.99 (the fees' -18,044.00 and the
  adjustments' +63.26 left out), return rate 0.159 -> 0.150, DOTCOM POSTAGE
  no longer the top product, new customers 191 either way.
  Consequences that follow from the rules and are recorded (review cycle 2):
  a discount booked -1 @ +price is no return line once classed, so every
  figure that reads return lines moves - the return rate, and the first-day
  rule: a first receipt carrying one no longer "opens with a refund", so its
  customer is new (#1). A discount, fee or adjustment line's blank order id
  no longer counts in the blank-id rule (it reads sale and return lines), so
  classing such lines can move a file from basis "lines" to "order_id" (#5),
  as a coupon's blank id never counted.

- **`orders_basis`** (2E-e): "order_id" when the optional field `order_id` is
  mapped and passes stage 1's check - then orders are the distinct order keys
  that have a sale row, an order key being the id ON ONE DAY FOR ONE CUSTOMER
  (an id reused elsewhere - two tills sharing a receipt numbering - is two
  orders, never merged; 2E-e doubt-review) and a line with no customer takes
  its receipt's one named customer that day (header-style exports). If ANY
  sale or return line has a blank id, the file counts lines, with the count in the
  reason - superseding decision 1's "a blank id is an order on its own" on the
  safe side after review (ids blank until a POS upgrade made orders fall 279
  -> 93 on an unchanged business); Online Retail II and the Kaggle demo have
  none; else "lines", every sale line an order, with
  `orders_basis_reason` saying why a mapped order_id was refused (more than
  10% of its ids span several days or customers). **When the check could
  read dates only** - judged PER RECEIPT, as the check itself is (Thach,
  2E-k; "mostly" = more than half): among the order ids with a sale line,
  most name no customer (after the receipt fill; a confirmed walk-in
  placeholder counts as none), or one customer is on most of them, or fewer
  than two different customers are named, or there is no customer column -
  a daily batch or Z-report code passes the check: the id is trusted only
  when the user confirmed in Review that it is a receipt number
  (`confirmations.order_id_is_receipt`, sections 4-5; Thach, 2E-e2 -
  unconfirmed means untrusted), else lines, with the reason. The user's No
  always counts. A header-style export names every receipt, so it passes
  although most of its lines are blank. The blank-id count in the reason is stage 2's own, on
  cleaned.csv: the exact number of sale and return lines with no id, written
  whatever the answers. Stage 5 and the frontend
  LABEL by it: basis order_id - orders, AOV, orders per customer, units per
  order, return rate; basis lines - lines, average line value, lines per
  customer, units per line, return lines per sale line. RFM frequency counts
  orders on the same basis. Measured on Online Retail II with Invoice mapped:
  AOV 376-565 against 16-21 on lines, frequency 1.3-1.6 against 26-39, one-
  time buyers 27.6% against 2.0%; the Kaggle demo (one line per Transaction
  ID) is unchanged.
- `return_rate_*` on basis order_id is orders holding a return line / orders
  holding a sale line (2E-e); on lines, return lines / sale lines.
- An **order** is a sale row: a revenue-counted row with quantity > 0 AND a
  positive line amount (Thach, 2E-c). Without `order_id` a row is the unit of
  purchase (2E-e: with it, the order id is). A return line (quantity < 0) is not an order, and
  neither is a zero-quantity line, a zero-amount line (a free item, a stock
  adjustment) or a line with a negative amount (a coupon, a discount, a
  bad-debt write-off) - a **deduction**. Its money stays in net revenue.
  `orders_*` count sale rows; so do buyers, RFM frequency and recency, and
  the period's ends. Measured on Online Retail II: 2,561 of its 2,631
  zero-amount lines carry no customer, 61 of the other 70 ride on an invoice
  with a paid line, and its five negative-amount lines are "Adjust bad debt".
- `aov_*` = **net** revenue / orders. Net, because only then does customers x
  frequency x AOV equal net revenue exactly (stage 3's lever lens).
- `return_rate_*` = return lines / orders: returns per order sold, the retail
  convention. A **return line** is a counted row with quantity < 0 AND a
  negative amount (Thach, 2E-c2, symmetric with the sale row): a zero-amount
  negative-quantity line is a stock write-off ("damaged", "missing"), not a
  customer return - 3,393 of them inflated Online Retail II's return rate by
  7% to 78% a month. **Range [0, infinity)**, not a proportion: it exceeds 1 in a
  month where customers return goods bought earlier. No reader may cap it or
  treat it as a share. Rejected alternatives (2E): return lines / (sales +
  returns) is bounded but its denominator grows with the returns it
  measures and it is not "per order"; a value-based rate (refunded money /
  gross sales) measures money, which P3 and the gross/net figures already
  carry, not how often goods come back.
- **Which customer a line belongs to** (2E-f): the normalised identity
  (3C2); with a trusted `order_id` (`orders_basis` "order_id"), a line with no
  customer takes its receipt's one named customer that day, read from the
  receipt's sale and return lines (its other lines only when none of those is
  named); two different names leave the line unattributed. Only the lines
  of an id's **receipt day** are filled: an id with sale lines is one
  receipt when they all fall on one day with at most one named customer,
  no sale or return line of it falls before that day, and its sale and
  return lines name at most one customer on any day - that day is its
  receipt day; an id with no sale line, when all its dated lines fall on
  one day with at most one named customer. Unnamed return lines rung under
  such an id on later days cannot be told apart from a receipt refunded
  later, and are not filled. The file-level 10% check tolerates ids that span, so
  without this a cash id "0" rung on many days made 30 walk-ins' revenue one
  named customer's, and a returns-desk "RET" or a coupon "DISC" id did the
  same with a walk-in's refund or coupon (2E-f doubt-review). A refund rung
  days later under the receipt it refunds leaves the receipt one - it is
  just not filled on its own day. This decides whose REVENUE a line is,
  never how orders count: the order key keeps the receipt's customer, as in
  2E-e. A line with no parseable date belongs to no receipt day. **Since
  2E-e2 the user can withhold the fill** by answering in Review that the
  customer is not written on a receipt's first line only
  (`confirmations.customer_on_first_line_only` = `false`; Thach, mitigating
  the known limit below); unanswered, it fills. Withheld, the lines stay
  unattributed and **`customers.unfilled_receipt_lines`** counts the
  revenue-counted ones the fill would have given a customer, with
  `unfilled_receipt_lines_reason` (null exactly when the count is 0), so their
  money is never lost silently. **A customer value the user confirmed as a
  walk-in placeholder** (2E-k; "Guest", "Walk-in", "0") names no one: its
  lines have no customer in every figure of both stages, and
  **`customers.placeholder_lines`** counts the revenue-counted ones, with
  `placeholder_lines_reason` (null exactly when the count is 0).
  **Known limit (for Thach, 2E-f doubt-review cycle 2 F2):** a per-day batch
  id (a Z-report, a shift, a daily returns desk) with one named line and
  unnamed walk-in lines looks exactly like a header-style receipt on its
  day, so the walk-ins' money is filled to that customer. Every customer
  figure - active customers, buyers, RFM, `new_vs_returning`, and stage 3's
  bridge, lever and members - reads this one per-row customer. Measured on
  Online Retail II rewritten header-style (the customer on each invoice's
  first line only): new revenue in 2011-11 read 8,783.75 against 79,845.90
  and every segment's money about a tenth; with the fill every figure equals
  the original. Without a trusted order id there is no receipt to inherit
  from, and a blank customer stays unattributed.
- An active customer has any revenue-counted row (3C, unchanged). A
  returns-only customer is active and has no orders. **`buyers_*`** counts the
  customers with at least one order (a sale row) - the count stage 3's lever
  divides orders by, so purchase frequency cannot fall because customers who
  only returned goods appeared (2E doubt-review F1). **Which of the two the
  Insights "customers" KPI shows is a stage 5/6 display decision** (Thach, 2E):
  buyers is the usual commercial meaning.
- RFM **frequency** counts the customer's orders (sale rows), and RFM
  **recency** the days since the last one (Thach, 2E-b): a refund is not a
  purchase. **R and F quintiles are cut from buyers only**, and a customer
  who never bought (only refunds) scores 1 on both by rule and lands in a
  segment of their own, **"No purchases in file"** (Thach; named "Returns
  only" in 2E-b, renamed in 2E-c2 because a gift-only customer returned
  nothing; `segment` is a plain
  string, as with 2B's "Needs Attention"). Ranked among buyers, 20 refunders
  pushed 10 lapsed one-time buyers up to Champions; in Hibernating they
  inflated its count and dragged its `avg_monetary` and `revenue_share_pct`
  negative. This supersedes 2B's "scored like any other customer" and
  "quintiles on the run's own data" for R and F. Monetary stays net (every
  counted row) and is never quintiled, so it has no population to choose.
  **Identical customers get identical scores** (Thach, 2E-c, superseding 2B's
  tie-break by position): every position is scored as before - five equal
  groups over the ranks - and a tied group takes the mean of its positions'
  scores, exact halves rounded down, so a tie never lifts a group. A file
  with no ties scores exactly as before; a population that ties throughout
  scores 3 on that dimension. **Exactly one order scores F = 1** (Thach, 2E-f):
  "bought once" is a fact of the data, not a rank. Ranked, one-time buyers
  above 40% of buyers tied at F = 2 and could never be "New", and a file
  where everyone bought once called 12 of 20 "Loyal". The fact also
  overrides 2B's 5/5 for a single customer (a convention for "no one to
  compare against"), so one customer with one purchase is New. No customer
  of Online Retail II (27.6% one-time buyers by invoice) or the Kaggle demo
  (25 customers, 422+ orders each) changes segment. A customer who never bought now also includes
  one who only got free items or coupons: "No purchases in file" is true of
  them too.
  Old metrics.json files keep the old segments until re-analysed.
- **`new_vs_returning`**: a customer is **new** when their first purchase (first
  sale row) falls in the current month AND their history does not open with a
  refund (`shared/first_purchase.py`, Thach, 2E-c, rule C). A refund proves a
  purchase before the file, so a refund-only customer is returning and their
  negative money is `returning_revenue`. **On the customer's first day**
  (their first day with a sale or return line) **each product nets on its
  own** (Thach, 2E-f): the history opens with a refund when, for any product,
  more units came back that day than were bought that day - a product not
  bought that day, or returned beyond what was; a return whose product is
  unknown (no sku, no name) cannot be matched and opens with a refund. The
  product is the shared `product_identity` (the sku, else the name). History:
  2E-c netted the whole day across products (10 pens bought and a 500 chair
  from before the file returned the same day netted +9: "new" with -490);
  2E-c2 took any return line on the first day as a refund, which also took
  "new" from customers returning part of what they had just bought. Measured
  on Online Retail II: 96 customers get "new" back, none lose it; netting by
  "was it bought that day at all" would free 10 more who returned MORE than
  they bought that day (pre-file evidence). The day is the unit, not the
  time of day. The same
  rule decides `new` in stage 3's customer bridge. Measured on Online Retail
  II: the first row of any kind called 172 refund-only customers new with
  -91,486.72 of "new revenue".
- **A ratio whose denominator is zero - or negligible, i.e. floating-point
  residue next to the money that moved to produce it (`shared/numbers.py`
  `is_negligible`, the same test stage 3 uses; judged against the GROSS money
  of both months, because two nets that are themselves residue make residue
  look like a scale: shares of 1.8e20 and a -100% change, 2E doubt-review
  F5/F6) - is null with a reason**
  (Thach, 2E): `aov_*` and `return_rate_*` with no orders, `contribution_pct`
  when the total change is negligible, each segment's `revenue_share_pct` when
  whole-file monetary is negligible, and pareto `concentration_pct` with no
  products. **Products (2E-g, Thach):** keys and labels come from
  `shared/products.py`, shared with stage 3. A product name or SKU is read
  as a reader sees it - Unicode composed, invisible characters removed
  (the zero-width joiners kept), spaces as one, case fully folded - the
  products' own reading (Thach, option A). **Every other column (2E-i,
  Thach): one reading for every stage** (`shared/text.py`). A cell is blank
  when it shows nothing - only whitespace, format characters that draw
  nothing (joiners, direction controls, tags - not the prepended
  concatenation marks, which draw a sign), variation selectors, or the
  products' invisible characters - in every column stages 2 and 3 read,
  and in stage 1's `drop_rows_missing` and plan checks (the profile's
  missing counts and the imputations still count NA tokens only - 2E-o Q5
  #10, a known limit). Two
  customers, order ids, categories or transaction types are one value when
  they differ in these ways a reader cannot see: Unicode composition, the
  characters that render as nothing AND change nothing around them (the
  zero-width space, word joiner, BOM, soft hyphen, invisible operators), the
  direction marks (a stray one rendered nothing; the rare id they reorder is
  the known cost), a no-break space for a space. Never the direction
  overrides, embeddings and isolates (they can reorder: a wrapper that
  renders alike still splits - a limit for Thach), the joiners or the
  variation selectors (they can change what is shown), never another whitespace
  kind inside a value (a control character, the wider ideographic space - at
  the ends every whitespace kind is trimmed), never full case folding. Some
  characters that draw nothing still split a value (the Hangul filler,
  tags, the combining grapheme joiner; a trailing joiner) - a known limit
  (2E-o Q5 #6, #7). Customers and categories are then lower-cased, a category's runs
  of spaces read as one, an order id keeps its case. A line's product is its SKU,
  else its name (a name-only line takes the SKU when its name, on sale lines
  that have one, maps to exactly one SKU); a line with neither is the
  `(no product name)` data gap - in every total, in no table (top products,
  decliners, velocity, the Pareto count). A product's label is the name its
  sale lines carry most over the whole file, a tie going to the most recent
  sale, so it reads the same in both months; with no named sale line, the
  commonest name on any line, else the SKU; a name several products share
  shows each one's SKU ("BATHROOM METAL SIGN (21171)"). `top_products.units`
  count sale lines. **Stock figures are not supported in v1** (Thach, the
  line taxonomy's scope cut, 16.0): `velocity` is null on every file with
  `velocity_reason` saying so, and the contract refuses a velocity list - 2C
  derived stock on hand from stock-in lines, which most POS exports do not
  have, and read a zero-amount -20 write-off as 20 back in stock. The
  `ProductVelocity` shape stays for v2.
- **The line taxonomy** (16.0, 2E-t2; `docs/LINE_TAXONOMY.md` sections 3
  and 5): stages 2 and 3 read each line's class from cleaned.csv
  (`line_class`, `class_source`, `suggested_class`) through
  `shared/transactions.py` and the effects matrix `shared/line_effects.py`.
  A value outside a column's closed list, or some of the three columns
  without the others, is refused - ANALYSIS_FAILED, "re-upload the file";
  a raw file's own columns of those names are the user's and are never read
  (stage 1's order checks classify the raw file). `core.identity` holds the
  compared months' revenue identity - net revenue = gross sales - returns -
  discounts - other deductions (unconfirmed) + other revenue, to float
  residue judged against `money_moved` (the month's counted amounts summed
  as sizes: a charge and its reversal cancel inside one term), refused
  otherwise - with `returns_on_suggested_keys`, the returns on keys the file
  suggests are costs, charges, discounts, adjustments or gift cards and
  nobody confirmed (Thach's Q26). `core.outside_revenue` lists each class
  outside revenue (gift cards, costs, adjustments, stock received) per scope
  (`file` - every line, the undated too - `current`, `previous`), only where
  it has lines, with the sum of its finite amounts and how many carry none;
  stock received is split by `sign` (`positive`, `negative`, `no_money` - an
  amount of zero or none), the other classes carry `sign` null. It is not
  `non_product` (the classed lines of the dated months, 2E-d2), and an
  undated line outside revenue is also in `undated_lines` - two questions,
  its class and its date. `core.unclassified` is the tested, empty class (0
  lines while v1 refuses no shape; its share null when nothing moved).
  `core.unmeasurable` counts the lines with no finite quantity, no finite
  price or an amount too large to add, per scope and reason - their money is
  unknown, never derived; `undated_lines` no longer counts them (reported
  once). `core.notes` are the standing rule's notes (CLAUDE.md 3.3a): one
  per code present - `same_day_cancellations` (every file with dated
  return lines), `returns_booked_as_in`, `unconfirmed_suggestions`,
  `unconfirmed_deductions`, `discounts_in_prices` (every file),
  `other_transaction_types` - each with the figures it qualifies (fixed
  per code in `contracts/lines.py`, which refuses any other; one note per
  code), its default sentence (written from `NOTE_TEXTS`; a reader accepts
  any non-empty one and renders by code - section 11, Thach's adjustment 2),
  and named measures per scope (lines, the
  signed sum of their amounts, orders and keys where defined -
  `other_transaction_types` names the five commonest values, cut to 40
  characters, and measures the rest together; `same_day_cancellations`
  counts apart the returns no match can check - no named customer, or a
  pooled code); no note changes a figure. `products.suggested_classes` maps every product the
  block names (top products, biggest decliners) whose own key carries an
  unconfirmed suggestion, by label, to that class - shown "(suggested:
  <class>, not confirmed)" (Thach's Q17); a name-only line resolved to a
  SKU keeps its own name's suggestion, which marks no product.
  **This supersedes 2A's decision that a zero denominator reports
  0.0**, which Thach approved in 2A because the 1.0 contract required a
  number there; 2.0 allows null, and 0.0 was a false statement ("AOV 0",
  "nothing moved") rather than the absence of one. A flat month's float
  residue (5.6e-17) is what produced shares of 1e15 twice in stage 3 (3C,
  3D), which is why "zero" means negligible, not `== 0`.

**A comparison that cannot be made is null, and a `*_reason` says why - never a
sign-inverted or half-month number.** The model enforces the pairing: a null
without a reason, a reason beside a value, or a list comparison null for only
some of its members is invalid.

- **Non-positive base.** `revenue_change_pct` (and each decliner's
  `revenue_change_pct`) is null when the previous value is zero, negative, or
  floating-point residue next to the money that moved in the two months
  (under a billionth of it). **Known limit (2E doubt-review cycle 4, session
  2E-b):** the money moved counts a self-cancelling outlier pair at twice its
  size, so ONE reversed barcode-sized typo (8,934,567,890,123 sold and
  refunded) makes a real +310 (+10%) month "residue" in both stages: this
  field and `contribution_pct` become null with a false reason, and a real
  -30% decliner drops out of `biggest_decliners`. A real but tiny base is NOT
  refused yet: a July
  netting 0.01 against an August of 3,100 reports +30,999,900%, which is true
  arithmetic on an unusable base. Applying 3D6's usable-base rule to stage 2
  is scheduled (PROJECT_PLAN 2F). Against a negative base the
  sign inverts: -100 -> -200 read +100% (a doubled loss as growth), and
  -100 -> +500 read -600%. Against zero, 2A's 0.0 said "nothing moved" when
  revenue appeared from nothing.
- **Incomplete previous month.** `period.previous_complete` is false when the
  previous month holds no SALE row, or when the FILE's first sale comes at
  least 3 days after the previous month's 1st (an export cut mid-month) - the
  one definition, `shared/periods.py`, that stage 3's trust gate blocks on
  (`docs/AI_PIPELINE.md` 7.2). Sales, not counted rows: a month holding only
  refund lines is not a base (2E doubt-review F3). **Known limit:** a leading
  gap in the middle of the history (a history-rich file missing the previous
  month's 1st-19th) is not detected here. The month's own first sale was
  measured as the rule and falsely flagged 15-35% of sparse shops and 13-17%
  of shops closed three days a week (2E); a pattern-aware rule belongs to
  session 3E1b and will replace this one inside the same shared definition.
  Stage 3's D1 check does catch such a gap, and **stage 5 shows stage 3's
  trust badge beside stage 2's period-over-period KPIs**, which covers what
  stage 2 cannot see. **Second known limit, at the other end** (2E
  doubt-review cycle 2): the CURRENT month is chosen from the file's last row
  of ANY kind, so sales ending on the 20th plus one refund line on the next
  month's 1st make the month "complete" (reproduced: -35.5% and a decliner
  that stage 2 reports; stage 3 cautions on D1 and headlines rule 2).
  Coverage is therefore sale-based at the previous month's start and
  row-based at the current month's end; session 3E1b makes period selection
  sale-based at BOTH ends inside the one shared definition. Until then the
  trust badge beside stage 2's KPIs shows the -35.5% with its caution.
  `previous_incomplete_reason` states which case applies and what to do:
  re-export from the 1st of the previous month. Every field whose only
  purpose is to compare the two months is then null, carrying that same
  reason: `revenue_change_pct`, `biggest_decliners` (the whole list),
  `by_dimension.*[].contribution_pct` (`contribution_reason`) and
  `segments[].customers_previous` (`customers_previous_reason`). The raw
  previous-month totals (`revenue_previous`, `orders_previous`,
  `active_customers_previous`, `aov_previous`, `return_rate_previous`, and
  each dimension's `revenue_previous`) stay: they are true counts of what the
  file holds for that month.
- **Stage 5 must render every `*_previous` total from an incomplete month with
  a visible "partial month" label** (Thach, 2E), so a reader cannot compare
  the two raw totals by eye and draw the conclusion stage 2 refused to
  compute.

**`biggest_decliners`** is every product with previous-period revenue whose
revenue fell by more than float residue, ranked by the fall in money (`revenue_change`, most negative
first), at most 10. A percentage cannot rank them: it would drop a product
whose loss doubled and rank a recovering product first. The percentage is
reported beside the money where its base allows.
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
`ai_findings`; step 8 is the only AI call and writes only `ai_findings`.
Written by `stages/diagnose/assemble.diagnose_run` (3G-lite), atomically;
until 3F, in the designed degraded mode: `ai_findings` and `model_used`
null. Why
the attribution is Shapley and why the hypothesis catalog is fixed in advance:
`docs/adr/0004-shapley-attribution.md` and
`docs/adr/0005-pre-registered-hypothesis-catalog.md`. Why a `level`-mode
signal describes rather than decides, and what stage 5 must therefore not say
about one: `docs/adr/0006-level-signals-are-descriptive.md`.

```json
{
  "schema_version": "4.0", "generated_at": "...", "model_used": "claude-sonnet-5",
  "frame": {"current": "2011-11", "previous": "2011-10",
            "year_ago_current": "2010-11", "year_ago_previous": "2010-10",
            "history_months": 23, "previous_leading_days_missing": 0,
            "history_start": "2009-12", "history_end": "2011-10"},
  "trust": {
    "verdict": "caution",
    "checks": [{"id": "D1", "status": "caution",
                "evidence": {"zero_days_cur": 6, "excess_zero_days_cur": 5.2,
                             "excess_zero_days_prev": 0.0,
                             "estimated_revenue_gap": 18400.0,
                             "estimated_revenue_gap_prev": 0.0,
                             "sparse_history_months": [],
                             "history_months_with_rows": 23,
                             "learned_from_months": 22},
                "message": "About 5 days in the current month have no sales beyond this store's normal closing pattern (missing data, or days the shop was closed), worth roughly 18,400 in revenue."}],
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
                               "arrivals_with_no_first_purchase_in_the_file": 3,
                               "empty_period": []}},
    "returns": {"gross_prev": 1338000.0, "gross_cur": 1198000.0,
                "returns_prev": 48000.0, "returns_cur": 48000.0,
                "deductions_prev": 0.0, "deductions_cur": 0.0,
                "charges_prev": 0.0, "charges_cur": 0.0},
    "products": {"volume": -96000.0, "mix": -21000.0, "price": -8000.0,
                 "new_products": 12000.0, "discontinued_products": -27000.0,
                 "unidentified": 0.0}
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
                "products_share_of_change": 0.93,
                "classification": "broad"}
  },
  "hypotheses": [{"id": "P2", "family": "product_returns", "lens": "product",
                  "statement": "Sales mix shifted towards cheaper products",
                  "verdict": "partial", "contribution": -21000.0, "share": -0.15,
                  "evidence": {"mix_effect": -21000.0, "products_in_both_periods": 412},
                  "rule": "share = contribution / D, D = |change in gross sales|; supported if same sign and |share| >= 0.2, partial if >= 0.05"}],
  "not_testable": [{"id": "X1", "statement": "Marketing and promotions",
                    "reason": "no campaign data; discount columns are not canonical"}],
  "headline": {"rule": 7, "hypothesis_id": null, "lens": null,
               "message": "Revenue went from 1,290,000.00 to 1,150,000.00 (-140,000.00). No single tested cause explains most of the change. Partly consistent: sales mix shifted towards cheaper products (P2)."},
  "ai_findings": {
    "summary": "Revenue fell 10.9% this month...",
    "headline_explanation": "The mix effect accounts for 15% of the drop in gross sales...",
    "hypothesis_notes": [{"id": "P2", "text": "Shoppers bought more of the cheaper lines..."}],
    "not_tested_note": "This data cannot test marketing, competitors, weather or footfall."
  },
  "notes": [{"code": "discounts_in_prices", "figures": ["gross_sales", "discounts"], "text": "...",
             "measures": []}],
  "suggested_classes": {"DOTCOM POSTAGE": "charge"}
}
```

`notes` (17.0, 2E-t2) are metrics.json's, beside the figures they name - the
`return_rate` signal and the headline's revenue among them; the narration
states them with their measures (`prompts/root_cause.md`) - except an always-on note - present by construction, not because of this file's data (`discounts_in_prices`; `same_day_cancellations` whose every measure counts 0 lines),
said once, in "How to read these figures" (docs/LINE_TAXONOMY.md section 3).
`suggested_classes` (17.0) maps every product this file names - the product
dimension's members, new and removed members, R1's top member, R3's products
(`contracts.diagnosis.named_products`) - whose own key carries a line-class
suggestion nobody confirmed, by label, to that class; the narration names
such a product with its mark and never makes it a product recommendation.
Both fields are required: a file without them is refused, never read as "no
note", and so is a mark on a product the file does not name.

**Types.** `frame.current`/`previous`/`year_ago_*`/`history_start`/`history_end`
are `YYYY-MM` strings; `year_ago_current` and `year_ago_previous` are `null`
together when the year-ago pair is not in the data. `history_months` is a
non-negative integer. `previous_leading_days_missing` (non-negative integer) is
the number of days of the previous month before the file's first
revenue-counted row (a sale or a return; not a stock-in row), capped at the
month's length; at
D1's caution size the D1 check blocks, since the comparison base is an
incomplete month (`docs/AI_PIPELINE.md` 7.2). `trust.verdict` is `trusted | caution | blocked`; each
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
`calendar.method` is `weekday_weights | day_count | not_applicable`.
`not_applicable` (15.0, 2E-j) is a month-grain file (`metrics.period.
month_grain`): `expected_cur` and `expected_prev` are null, `calendar_effect`
is 0 and `evidence.reason` says the file records months, not days - its
weekday weights were all 0 (every day but one holds nothing) and T1
"ruled out" the calendar on no evidence. In such a file the D1 check's
status is `not_applicable` (15.0) with that message - it read "normal"
having measured nothing - and the trust verdict does not count it (not
`inconclusive`, which would badge every monthly file `caution`); hypotheses
D1, T1 and R3 are `not_testable`, saying so; T2's year-ago zero-day guard and
B1's missing-day refusal, day-level too, do not apply, and their evidence
says so. `tree.method` is always `"shapley"`.

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
`(uncategorised)`, `(no product name)`, `(no customer)`. Since 2E-l the
product dimension's `(no product name)` also holds the pooled items (many
items under one code): sold, never ranked - a label that says "no name" for
lines that have one is a known limit (2E-l review cycle 1, Phase 8). The product
dimension's `(not a product)` bucket (2E-d2: the lines the user classed as
charges or discounts - revenue, no missing data, but no product) carries
`is_not_a_product` instead, never both; it too stays out of `new_members`,
`removed_members` and recommendations. Those buckets exist so
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
and the only one always present, and over *every* product - never the
`(no product name)` data gap, which is no product whose share of the change
could be concentrated (2E-g; R1's top product likewise) - rather than the named
few - measured over the top five, every change would look concentrated, since
the top five are chosen for being the largest movers. Since 2E-l (Thach) it is
measured against the products' OWN change, and only when more than half of
the change sits in them (above floating-point residue); otherwise the
classification is `outside_products`. Since 2E-n
`products_share_of_change` is the change in the products' SALE lines over
the total change - customer returns are their own class (Thach) - null for a
flat month. It is the one definition of the share of the change in the
products (Thach, 2E-m): R1 and the headline's product-lens gate (rule 6) read
breadth's decision, never a measure of their own. `declining_base_share`,
`top_member_share` and R1's top product stay over each product's own net
change, as the product dimension (which reconciles to the net change): read
on sale lines, a cancelled order became a product's "change" (2E-n review
cycle 1).

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
`arrivals_with_no_first_purchase_in_the_file` - customers absent from the
previous month whose history opens with a refund (or holds no sale at all).
Since 2E-c they are **resurrected, not new** (rule C, CONTRACTS section 6's
`new_vs_returning`): a refund proves a purchase before the file. This
supersedes 3C's `new_customers_whose_first_activity_is_a_return`, a note on
`new` that changed no term; moving a customer between `new` and
`resurrected` changes no total, so the identity holds. It also carries
`customer_values_merged_by_normalisation`: how many distinct raw customer
values the shared `customer_identity` key collapsed across the whole file
(distinct raw values minus distinct identities, so a customer written three
ways contributes 2). A large number says the customer column is inconsistently
entered, which is context for every C-family verdict built on it. `hypotheses[].verdict` is
`supported | partial | ruled_out | inconclusive | not_testable`; `contribution`
and `share` are `null` for directional hypotheses (D2, D3, T3, C4, R1), which
carry their test in `evidence` and `rule` instead, and for any hypothesis
whose verdict is `inconclusive` or `not_testable`; `share` is also `null` when
the change is negligible or `D` is zero. `statement` is the RENDERED
statement: for a cause that can move either way, code picks the fall or rise
wording from the sign of `contribution`, and the direction-neutral tested
statement is kept when no number was computed (ADR-0005 clarification).
D1's `evidence` carries `estimated_revenue_gap` and
`estimated_revenue_gap_prev` (each month's gap at its own month's pace) and
`d1_status`; T2's carries `excess_zero_days_year_ago_cur` and `_prev`; B1,
when refused on a possible gap, carries `d1_status` and both months'
`excess_zero_days`; B2, while inconclusive on refund lines, carries
`refund_lines_prev` and `refund_lines_cur` (counts of return lines and
negative-amount lines, each once; 2E-c2 kept the negative-amount clause when
the proof for dropping it failed). B1 is no longer refused on refunds (2E). The D1 trust check's `evidence` lists
`sparse_history_months` (history months too gapped to learn from),
`history_months_with_rows` and `learned_from_months`; on a block for an
incomplete previous month it carries only `previous_leading_days_missing`,
`first_sale` and `previous_month_has_sales`. `family` is one of `data_quality | time | customers
| lever | product_returns | localization_lifecycle`; `id`, `family`, `lens`
and `statement` come from `stages/diagnose/catalog.py`, the catalog's single
home, which `docs/AI_PIPELINE.md` 7.8 mirrors under test. `headline.rule` is `1`-`7`
(`docs/AI_PIPELINE.md` section 7); `hypothesis_id` and `lens` are `null` for
rules that name no hypothesis (1, 2, 3, 4, 5, 7), and for rule 6 when it
names an exact tie, or when no cause it may name fits and it names the
movements that offset each other (2E-n) - the message names them. Every `evidence` value is a
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
  `delta_net` (`delta_gross - delta_returns - delta_deductions +
  delta_charges`; gross is the sale rows, returns the return lines, charges
  the lines classed as paid by the customer - 2E-l, `diagnosis.json` 11.0 -
  and deductions every other counted row - 2E-c, `diagnosis.json` 2.0). A reader must not add shares across lenses, and stage 5 must not
  present them as one total.
- `tree.customers` is `null` when no column is mapped to `customer`, and
  `tree.lever.level1.formula` is then `"orders*aov"`. `tree.lever.level2` is
  `null` when net units are not positive in both periods (inconclusive).
  `localization.mix_rate` is `null` when no category column is mapped.
- When `trust.verdict` is `blocked`, `calendar`, `signals`, `tree` and
  `localization` are all `null`, every hypothesis outside the D family is
  `inconclusive`, and `headline.rule` is `1`.
- Stage 2 reports no stockout risk in v1 (`metrics.json` `products.velocity`
  is null on every file, section 6: stock figures are not supported in v1 -
  the line taxonomy's scope cut, 2E-t2). Hypothesis R3 here is a *sales-gap*
  signal - it reads the sales pattern, never stock, so it stays (Thach's
  Q27) - a product that sold on most days and then stopped while the store
  kept trading; stage 5 words it "consistent with a stockout, verify on the
  shelf", never as a stock figure.

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
    "method": "weighted moving average of the last 3 complete months (weights 1, 2, 3) with a monthly seasonality index",
    "horizon_periods": 3,
    "revenue": [
      {"period": "2011-12", "point": 401224.73, "low": 313360.52, "high": 513725.48, "confidence": 0.8},
      {"period": "2012-01", "point": 319850.95, "low": 248535.58, "high": 411629.72, "confidence": 0.8},
      {"period": "2012-02", "point": 257218.16, "low": 205095.21, "high": 322587.64, "confidence": 0.8}
    ],
    "insufficient_history": false,
    "months_used": 24, "history_note": null, "season_note": null,
    "products_at_stockout_risk": null,
    "products_at_stockout_risk_reason": "stock figures are not supported in v1"
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
**The forecast as built (4A, `stages/predict/forecast.py` and
`seasonality.py`; redesigned after each of its first two reviews, validated
on swept series; its third review's limits are 8D's).** Revenue only
(per-product demand served the stockout risk, not supported in v1). It reads
metrics.json's `period` and `core.revenue_by_month` only (section 11).

- **History.** The contiguous run of complete months holding revenue, ending
  at `period.current` - complete as stage 3's history reads it
  (`shared/periods.complete_months`: covered from the first day to the
  last, every month in a month-grain file). A complete month with no
  revenue ends the run - a closed month or missing data, which the file
  cannot tell apart (the standing rule), never a zero. When months with
  revenue lie before it, `history_note` says which month cut them off and
  how many are not used; otherwise it is null. `months_used` counts the
  run, the compared month included (diagnosis.json's
  `frame.history_months` leaves it out and counts a different span: the
  two are not the same figure).
- **No forecast** under 3 months: `insufficient_history` true exactly when
  `months_used` < 3 (enforced), `horizon_periods` 0, `revenue` [], and
  `method` says no forecast was made.
- **Otherwise 3 months ahead**, one point a month, consecutive (enforced): a
  weighted level of the latest three months (weights 1, 2, 3), each over
  its calendar month's index when a season is claimed, times the forecast
  month's index. No trend term: a flat level is the interpretable reading
  of a weighted moving average (a step between the years on top of a
  season can still tilt the indices - 8D).
- **A season is claimed only when every test holds** (SPECS 7.5 and 7.4a):
  at least two full years, counted back from the current month, every
  month of them positive; measured against the business's own trend - the
  median change of the logarithms from a month to the same month a year
  later, over twelve (the season cancels in a same-month change, and a
  median ignores one big month); the gap (strongest index - weakest) /
  strongest above 40%; the same pattern in every year (each year's months
  against the other years' mean, a mean correlation of at least 0.6, so
  noise or one big month is no season); and not a steady ramp through the
  counted year (a straight line explaining 90% or more of the indices'
  logarithms) - the shape a step between two years leaves, which two
  years of data cannot tell from growth over a falling season (the
  standing rule: no season is claimed, and `season_note` says why; null
  otherwise - a season refused by another test is no ambiguity, so no
  note; the gap is tested first). `history_note` and `season_note` are
  sentences written by code, shown as written and never parsed, like a
  `*_reason` - their presence is what a consumer decides on (`months_used`
  carries the count); stage 4 never writes a season note beside a claimed
  season (its tests pin it; the model does not check the method's
  wording). Every index a positive number a float carries, or none is
  measured.
- **The band**, `confidence` 0.8, from the method's own errors h months
  ahead over the history: the log of actual over forecast when the last
  twelve months are all positive (windows holding a month not positive
  left out; the band then stays above zero and a lag behind a trend grows
  with h as it does in the data), in money otherwise; a seasonal year's
  errors from the OTHER years' indices, a month older than the counted
  years from all of them. Their root mean square times Student's t for as
  many errors, around the point in logs or in money. With fewer than two
  errors (3-6 months of history, the longer horizons first), the history's
  own spread in money times sqrt(h) - which can put `low` under zero on a
  positive history, and can make a later month's band narrower than an
  earlier one's. The errors are pooled over the calendar months: 80% is
  over the year, and a peak a season too mild to claim leaves unmodelled
  is rarely inside its month's band (8D).
- **Validated on swept series** (400 each, seeded, reproducible: flat,
  trending, seasonal, seasonal and trending, steps, one big month; 3 to 36
  months): at every horizon the band held the true month 73-94% of the
  time on flat series, 78-98% on trends of 12 months or more (wider than
  80% on steep ones) and 79-87% on seasons; a real season (the Online
  Retail II shape) was claimed 84-100% of the time, and a false one at
  most 2% on noise and 4.2% on one big month on a flat business. **Known
  limits (8D; the third review, reproduced on the same sweep), where a
  season is claimed that the data does not hold:** a step between the two
  years at 10-20% noise, up to 59% of the time at 24 months (36-41% for a
  step of x0.5 to x2; for x3, 0.8% at 10% noise and 59% at 20%; up to 29%
  at 36 months; at 5% noise 0-1.2%); a step one month off the counted year's boundary,
  10-15%; one big month at the peak of a season too mild to claim, nearly
  always; and a real season with a step between the years is claimed with
  its indices tilted by the step, the band then holding 0-28% at 24
  months. Also: a trend with 3-4 months holds 54-67% (and 67% three
  months ahead at 6 months); a jump after the
  history is unforeseeable; a real season shaped as a ramp through the
  year is refused.
- **Figures** are finite, or the file refuses them as "too large" (the
  user's amounts - months hundreds of orders of magnitude apart).

Forecast numbers come from code; the AI writes only `recommendations` and
`do_not_do`, and no digit in them is its own (4B): every figure is an input
figure cited by path and rendered by stage 4, every proposal a bounded token
("20% (assumed)"), and every `expected_impact` is the AI's formula with the
result stage 4 computed (`docs/AI_PIPELINE.md` section 8). The example
above shows the fields' shape in the older free-text style. The step is
built but off by default in v1 (4B's review 3): until Thach decides, every
forecast.json carries these blocks null, the answer saying why.

When the AI step is unavailable, meaning no AI output was accepted after the
shared retry (`docs/AI_PIPELINE.md` section 9), stage 4 still writes this file:
`forecast` is always filled, and `model_used`, `recommendations` and
`do_not_do` are all `null`. They are either all `null` or all filled, never
partially filled. The keys are always written: `null` is a value, not a missing
key, and it is never replaced by an empty list. Minimum counts such as "3 to 5
recommendations" (`docs/AI_PIPELINE.md` section 8) are enforced by stage 4
before writing, not by this contract. The AI blocks are null the same way
when stage 4 does not ask the AI (4B): the diagnosis is blocked, or the
previous month is not complete - the endpoint's answer says which.

## 9. `report.json` (stage 5 output, data layer)

Defined in session 5A (`contracts/report.py`; in place at `1.0` - no report.json
had been written). An illustrative excerpt - its values from the example files
of sections 6-8, as a v1 run shows them (the AI strategy step off, no
narration yet); "..." elides:

```json
{
  "schema_version": "1.0", "generated_at": "...",
  "run_id": "...", "source_file": "sales_2011.csv",
  "data_quality": {"rows_in": 152430, "rows_out": 151988,
                   "issues_fixed": 2, "warnings": 1},
  "layer_1_numbers": {
    "period": {"current": "2011-11", "previous": "2011-10", "data_start": "2010-12-01",
               "data_end": "2011-12-09", "previous_complete": true, "previous_incomplete_reason": null},
    "trust": {"verdict": "caution",
              "checks": [{"id": "D1", "status": "caution", "message": "About 5 days in the current month ..."}],
              "limitations": ["..."]},
    "kpis": [{"id": "revenue", "label": "Revenue", "unit": "money", "current": 1150000.0,
              "previous": 1290000.0, "change_pct": -10.9, "change_reason": null,
              "current_reason": null, "previous_reason": null, "notes": []},
             {"id": "orders", "label": "Orders", "unit": "count", "current": 1820, "previous": 1950,
              "change_pct": null, "change_reason": null, "current_reason": null,
              "previous_reason": null, "notes": []}, "... the other three KPIs"],
    "current_note": null,
    "revenue_by_month": ["... 2011-09 to 2011-11, each complete",
                         {"period": "2011-12", "revenue": 300000.0, "revenue_reason": null,
                          "complete": false}],
    "undated_lines": 0, "undated_lines_reason": null, "unmeasurable": [],
    "non_product": [], "outside_revenue": [],
    "how_to_read": [{"code": "discounts_in_prices", "text": "...", "figures": ["..."], "measures": []}],
    "notes": []
  },
  "layer_2_causes": {
    "headline": {"rule": 6, "hypothesis_id": "P2", "lens": "product", "message": "..."},
    "hypotheses": [{"id": "P2", "statement": "Sales mix shifted towards cheaper products",
                    "verdict": "supported", "contribution": -21000.0, "share": 0.21,
                    "rule": "same sign and share >= 0.20", "evidence": {"mix_effect": -21000.0}}],
    "not_testable": [{"id": "...", "statement": "...", "reason": "..."}],
    "signals": [{"series": "revenue", "mode": "level", "signal": "within", "value_cur": 1150000.0,
                 "center": 1240000.0, "lower": 1090000.0, "upper": 1390000.0, "rule": null,
                 "mode_fallback": null, "insufficient_reason": null}],
    "narration": null, "narration_status": "unavailable",
    "notes": [], "suggested_classes": {}
  },
  "layer_3_actions": {
    "forecast": {"method": "...", "months_used": 24, "insufficient_history": false,
                 "points": [{"period": "2011-12", "point": 1210000.0, "low": 1040000.0,
                             "high": 1380000.0, "confidence": 0.8}],
                 "history_note": null, "season_note": null, "notes": [],
                 "first_month_in_file": true, "partial_first_month_until": "2011-12-09"},
    "recommendations": null, "do_not_do": null,
    "recommendations_status": "switched_off", "notes": []
  },
  "charts": [
    {"id": "revenue_trend", "type": "line", "title": "Revenue by month", "notes": [], "note": null,
     "cautions": ["About 5 days in the current month ..."],
     "series": [{"name": "revenue", "x": ["2011-09", "2011-10", "2011-11"],
                 "y": [1000000.0, 1290000.0, 1150000.0]}]},
    {"id": "forecast", "type": "line", "title": "Revenue forecast", "notes": [], "note": null,
     "cautions": ["About 5 days in the current month ..."],
     "series": [{"name": "point", "x": ["2011-12"], "y": [1210000.0]},
                {"name": "low", "x": ["2011-12"], "y": [1040000.0]},
                {"name": "high", "x": ["2011-12"], "y": [1380000.0]}]}
  ],
  "provenance": {"stages_run": ["ingest", "analyze", "diagnose", "predict"],
                 "ai_calls": 2, "models_used": ["claude-sonnet-5"]}
}
```
Stage 5 performs no analysis: it selects, orders and formats. Any number in
`report.json` must be traceable to an earlier contract file - this is what makes
the report defensible. How the layers are built (`stages/report/layers.py`;
`builder.py` checks the files, assembles the layers, draws the charts and
writes the file):
- **The files must describe the same months**: diagnosis.json's
  `frame.current`/`.previous` those of metrics.json's `period`, and
  forecast.json's first point the month after `period.current` - otherwise
  `ReportMismatchError` (stage 4's `DiagnosisMismatchError`, for stage 5;
  5A review 1 #8): never another comparison's badge beside these KPIs.
- **`layer_1_numbers`** (metrics.json; the trust badge from diagnosis.json,
  beside the KPIs - section 6): the five KPIs, each current and previous side
  by side - "Lines", "Average line value" and "Return lines per sale line"
  when `orders_basis` is `lines` (section 6); counts stay whole numbers; the
  return rate's unit is `ratio` (returns per sale, no ceiling - not a
  share). The one change shown is `revenue_change_pct` (section 11); no
  other is computed. An incomplete previous month is never shown beside the
  current: every `previous` is null and `previous_reason` carries
  `previous_incomplete_reason`. A null figure carries its reason
  (`*_reason`). Two zeros stage 2 writes are shown as a null with a reason,
  never as a real 0 (section 11; the standing rule): a current month in
  which no line counted in revenue is dated - every current KPI and the
  change, "a closed month or missing data, which the file cannot tell
  apart" - or "the file starts on ..., after ...", "no line counted in
  revenue carries a date the file can read" (every line undated), "no line
  dated in ... can be measured" (its lines unpriced or without a quantity;
  5A review 4 #3) - and active customers of 0 in
  a month with lines, none of which names a customer ("no column is mapped
  as the customer" when cleaning_report.json maps none; "no line in ...
  names a customer" otherwise; 5A reviews 2 #5, 3 #3). A day-grain file
  that starts part-way through the current month keeps its figures - stage
  2 takes that month as a fair one (a shop that opened then) - with
  `current_note` beside them: the file cannot tell that from an export cut
  short (the standing rule; 5A review 3 #1). The trust badge carries its verdict, every check's id, status and
  `message` (why a caution: a cut-short month, a gap) and the limitations.
  `revenue_by_month` lists every month from the file's first with revenue
  to its last; one inside with no line counted in revenue has `revenue`
  null and a `revenue_reason` ("a closed month or missing data, which the
  file cannot tell apart"), never 0. `complete` is true only when both
  definitions say so - `shared/periods.complete_months` (stage 3's history,
  the forecast's) and, for the compared month, `period.previous_complete`
  (stage 2's) - and never past `period.current`: nothing is drawn whole
  that either calls partial (5A reviews 1 #1, 2 #3). `undated_lines` (with
  its reason) and `unmeasurable` are the lines in no figure (section 6:
  never dropped silently); `non_product` and `outside_revenue` the money of
  the classes that is not product revenue, each reason saying where it went
  (an adjustment is a reconciling amount). These rows, and the notes'
  measures, are carried whole, a scope per figure; a renderer shows a
  `previous` scope (or `amount_previous`) only when `previous_complete` -
  never a previous value beside a current one (section 11; 5A review 3 #4)
  - and, when the current KPIs are withheld, `non_product[].amount_current`
  as withheld with that reason, never its 0; a `current` scope of lines
  (unmeasurable, outside revenue, a note's measures) is shown: those lines
  are real, and often why the month is withheld (5B review 1 #5). Notes are worded from
  `NOTE_TEXTS` by code, never the file's sentence: an always-on note ONCE
  in `how_to_read` (Thach, adjustment 1; deduplicated across metrics.json
  and diagnosis.json), the others in `notes`, each KPI listing by code the
  notes whose `figures` name it.
- **`layer_2_causes`** (diagnosis.json as it stands): the code-written
  headline; the hypotheses with their `rule` (why a figure is null, or a
  directional test) and `evidence`, shown key by key (section 11); the
  not-testable list; the signals (a description, never a verdict -
  ADR-0006/0007) with `rule`, `mode_fallback`, `insufficient_reason`,
  `limits_method` (a floor, `minimum_spread`, told apart from a measured
  chart - section 7) and `label`, the series named as the KPIs are ("Lines",
  "Lines per customer", "Average line value", "Units per line", "Return
  lines per sale line" when `orders_basis` is `lines`; 5B review 2 #1, #2);
  diagnosis.json's `notes` that are not always-on (the copies of
  metrics.json's notes stage 3 carries); the suggested classes.
  `narration` is `ai_findings`; null shows as `narration_status`
  "unavailable" (AI_PIPELINE 9).
- **`layer_3_actions`** (forecast.json): the forecast with its notes -
  metrics.json's notes naming revenue (not always-on) and its own
  `history_note` / `season_note`. `first_month_in_file` says the first
  forecast month is one the file holds lines of - its revenue so far is
  never compared with the point; `partial_first_month_until` is the day a
  day-grain file ends in it (a month-grain file's month-to-date line has no
  such day: 2E-o). The recommendations and do-not-do are shown only while
  stage 4's AI step is on - the backend tells the stage (4C review #4):
  `recommendations_status` "shown", "switched_off" (whatever the file
  holds), or "unavailable" (no accepted answer); `notes` beside them: every
  note of either file that is not always-on (section 11). A recommendation's
  `confidence` is replaced by `confidence_label` - "high" from 0.7,
  "medium" from 0.4, "low" below (display cut points, 5A) - never a figure.
- **`charts`**: `revenue_trend` from the first complete month with revenue
  to the last; a month between them with no revenue or not whole is a null
  point, drawn as a gap, and `note` says why - each run of months with no
  line once ("No line counted in revenue is dated in 2011-06 to 2011-08 (3
  months): ..."), the compared month with its own
  `previous_incomplete_reason` - never joined, never a zero; with no month
  to draw, `note` says so. `forecast` (point, low, high), when there is a
  forecast, with the forecast's own `history_note` and `season_note` as its
  `note`. Both list in `notes` the notes naming revenue and in `cautions`
  the messages of the trust checks that caution or block, and of D1 when it
  cannot judge whether the month was cut short ("inconclusive"; D2's is
  about prices, the badge's alone): a cut-short month is plotted as it
  stands, and the forecast learns most from it (the standing rule; 5A
  reviews 2 #2, 3 #5, 4 #7).
- **`provenance`**: `stages_run`; `ai_calls` counts the AI answers the report
  uses - a schema inference, an AI-proposed plan, a narration, shown
  recommendations - not the calls made (retries and failures are in the
  server's logs); `models_used` the models that gave them. Stage 1's two
  files feed only this: one absent, or of another major, is read as absent;
  one of the current major that cannot be read fails the report, as a
  broken run does.
- **`data_quality`** (cleaning_report.json): rows in and out; `issues_fixed`
  the plan's changes that did something - changed a cell (a fill, a trim, a
  parse), or dropped or marked a row (a drop, a flag; stage 1's
  `rows_affected` counts both); an action that changed nothing is still
  logged (1D) and not counted; `warnings` their count.
- **What the contract refuses** (5A reviews 1 #14, 2 #7, 3 #9, 4 #5): KPIs other
  than the five, once each, in order; a change on any KPI but revenue; a
  comparison with an incomplete previous month; a null KPI, a null revenue
  change or an incomplete previous month without its reason; a previous
  month that is not the one before the current, or data that start after
  they end; a month revenue null without its reason or with one it does
  not need; months out of order or twice; a month past the current one, or
  a compared month the KPIs withhold, drawn whole; a note worded otherwise
  than by its code, or a code listed twice in any one list; an always-on
  note beside a figure, or a file's note in `how_to_read`; a note named
  beside a figure that the report does not show; a chart other than
  `revenue_trend` and `forecast`, either drawn twice, one plotting other
  figures than the report's own (the forecast's point, low and high only),
  or a revenue line - any series of it - joined across a month or out of
  order; a forecast that does not start the
  month after the current one; `first_month_in_file` other than whether the
  file ends in the first forecast month, or a day other than the file's
  last; a revenue chart other than one series named `revenue`, or a
  forecast chart other than `point`, `low` and `high` over the same months;
  forecast points when the history is too short, or none when it is not (5B
  review 1 #6). Not held by the contract: which months are covered whole (it
  would need `shared/periods`, a second copy of a frozen definition - the
  builder and its tests hold it).
- **`source_file`**: the uploaded file's name, passed by the backend from the
  run's row (stage 5 never reads the database).

**report.html** (session 5B, `stages/report/html_report.py`,
`html_causes.py`, `html_parts.py`, `html_charts.py`) is report.json rendered
as one self-contained page - no stylesheet or script fetched; plotly.js
inlined once - written beside it atomically by `html_run`. It is not a
contract file: it shows report.json as it stands and computes nothing (a
number is formatted: rounded for display; one that shows as zero shows no
sign - section 11). It keeps the rules above - a withheld figure shows its
reason, an incomplete previous month is never compared (its reason said
once, each withheld cell pointing to it), always-on notes once, the notes
beside the figures, the forecast and the recommendations by code, the
trust cautions and gap notes beside the charts, signals worded by the rule
that fired and never as a verdict (a floor said so; a rule or reason the row
leaves null left unsaid), a product whose class nobody confirmed marked
"(suggested: <class>, not confirmed)" wherever the evidence names it
(sections 6 and 7). Every string from report.json is escaped
(SPECS SEC-3, as 5B extended it to the uploaded file's text), and a chart
carries only months and numbers.

## 10. Versioning and change policy

- Adding an optional field: minor bump (`1.0` -> `1.1`), readers unaffected.
- **Adding a value to an enum** (Thach, 2E-e): if a reader validates the enum
  as CLOSED - rejects a value it does not know - the addition is breaking and
  is a MAJOR bump. Every contract here is validated with closed Pydantic
  `Literal` enums, so in practice adding an enum value is always major. (Only
  an enum a reader explicitly treats as open, passing unknown values through,
  could take a minor bump; none exists today.)
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
- 2026-09-29: **session 5B, report.html.** report.json gains two checks, in
  place at `1.0` (no report.json has been written outside the tests): a
  chart's series are its own (the revenue line one series, `revenue`; the
  forecast `point`, `low`, `high` over the same months), and a forecast has
  points exactly when its history is long enough, and it is too short
  exactly when fewer than `MIN_HISTORY_MONTHS` months were used. A signal
  row gains `label` and `limits_method` (5B review 2; section 11 gains the
  row `signals[].limits_method` for readers 5 and FE - additive).
  `contracts/forecast.py` names the threshold, `MIN_HISTORY_MONTHS` (3, SPECS
  7.4), read by stage 4 and the page.
- 2026-09-29: **session 5A, report.json defined.** Section 9's three layers,
  `dict[str, Any]` until now, are typed (`contracts/report.py`), in place at
  `1.0`: no report.json had been written. Stage 5 selects and orders the
  earlier files' fields and computes nothing (section 9 lists how each layer
  is built). Its reviews (5A reviews 1 to 4) added, still in place at
  `1.0`: the trust checks' messages; the hypotheses' `rule` and `evidence`
  and the signals' `rule`, `mode_fallback` and `insufficient_reason`; the
  lines in no figure and the money outside product revenue
  (`non_product`, `outside_revenue`); a month with no line as a null with
  its reason, and a chart's gaps, `notes`, `note` and `cautions`;
  `current_note`; `first_month_in_file` and `partial_first_month_until`;
  `confidence_label` in place of a recommendation's `confidence`; the
  return rate's unit `ratio`; and the validators listed in section 9's
  "What the contract refuses". The leaf rows are in
  `contracts/report_views.py` (split for file size; `contracts/report.py`
  re-exports them).
- 2026-09-29: **session 4C, forecast.json written.** Stage 4 writes the
  file for the first time (`stages/predict/assemble.py`, POST /predict),
  `schema_version` `1.0`: the forecast always; `model_used`,
  `recommendations` and `do_not_do` null together while the AI strategy
  step is off (v1's default, 4B's review bound) and whenever it is not
  asked or gives no accepted answer. No field changed. A re-run of stage 4
  removes the report's files (section 1).
- 2026-09-29: **session 4A, the forecast (4A reviews 1 and 2).** Section 8's
  `forecast` block gains `months_used` (the complete months the forecast
  learned from), `history_note` (why they start where they do, or null) and
  `season_note`, all required, and the block's shape is enforced: `insufficient_history`
  exactly when `months_used` < 3, then no point and `horizon_periods` 0;
  otherwise one point per month of the horizon, the months consecutive; every
  figure finite, or "too large". Added in place at `1.0`, as 2E-t2's
  forecast change was: no stage writes forecast.json yet (4C is the first).
  `season_note` (third review, the standing rule) says why no season is
  claimed when the months rise or fall steadily through the year - null
  otherwise, and null with no forecast. Section 11 gains one rule: a note
  naming revenue, and the forecast's own notes, stand beside the forecast.
- 2026-09-29: **session 3G-lite, diagnosis.json written (Thach).** Stage 3
  writes the file for the first time (`stages/diagnose/assemble.py`, POST
  /diagnose), from steps 1-7, `ai_findings` and `model_used` null. No field
  changed: the three demo runs' blocks equal the regression anchor's pinned
  stage 3 blocks exactly (as serialised JSON). The file refuses any number
  JSON cannot carry, as metrics.json does; amounts stage 3's attribution
  multiplies past a float are ANALYSIS_FAILED (`amounts_too_large`). A
  note carries EXACTLY its code's measures (`NOTE_MEASURES`; every writer
  already did). A re-run of stage 2 or 3 removes the later outputs
  (section 1).
- 2026-09-29: **session 3G0, the consumer contract (Thach).** Section 11
  lists the fields of metrics.json and diagnosis.json that stages 4 and 5
  and the frontend read; a test fails if one is renamed, removed or
  retyped, and the v1 rows are frozen - they change only additively. **A
  note's sentence is no longer part of either contract** (adjustment 2,
  relaxing 2E-t2's U12): its code, figures and measures are; the sentence
  is the default rendering, rewording it is not a major bump, a reader
  accepts any non-empty one, and no consumer reads it (a consumer words a
  note by its code). A note's measure names are a closed vocabulary per code
  (`NOTE_MEASURES`, checked on read - every writer already wrote exactly
  these), and every note carries `always_on` (a computed field of
  `contracts.lines.is_always_on`: shown once, in "How to read these
  figures", adjustment 1). No version change, by decision: `always_on` is
  derived from the note's own fields and every reader reads the files
  through the model, which computes it - no reader can see it missing, so a
  minor bump would tell no one anything.
- 2026-09-29: **session 2E-v, the scoped review of 2E-t1-t3's last fixes.**
  metrics.json refuses any number JSON cannot carry, anywhere in the file (a
  model check, `numbers_json_cannot_carry`): a month outside the two
  compared whose amounts overflow was written as null into a required float
  after a 200 - now ANALYSIS_FAILED (`amounts_too_large`), nothing written;
  a NaN is an overflow's trace too (+inf and -inf meeting in one segment),
  and a product's units that overflow are refused the same way. No version
  change: no readable file changes. A run file another version of the app
  wrote (an older or newer major, or a 16.0 metrics.json from before the
  line taxonomy's blocks) is never a 500, on any endpoint (one handler for
  the app): a stage 1 file is EXPIRED (410, `details.reason`
  `another_version`, `details.file` when one model reads one file) with the
  re-upload hint; a later stage's output (metrics, diagnosis, forecast,
  report) INVALID_STATE (409) "run that stage again". Each contract model
  says its file (`filename`) and the stage that writes it
  (`written_by_stage`). A file of another major is told its major before
  anything else, with what to do: an older one per file (re-upload, or run
  its stage again), a newer one "upload the file again".
- 2026-09-28: **session 2E-t3, Review shows the line taxonomy (Thach).**
  `contracts/lines.py` gains `LineSummary` and `ReservedRename`, the payload
  of `POST /line-summary` (SPECS section 8) - never a stored file, so no
  version. The line blocks' money figures must be finite: a sum too large
  to add is refused rather than written as the null no reader could load
  (3C C2), so stage 2 stops on such a file instead of writing it (8D).
  metrics.json and diagnosis.json are otherwise unchanged but for
  `undated_lines_reason`'s wording (what the whole file's reports still
  count): stage 2's report moved to `shared/line_report.py`, every demo
  figure identical. A stage 2 refusal of a sum too large to add is
  ANALYSIS_FAILED (422, `details.reason` `amounts_too_large`).
- 2026-09-28: **session 2E-t2, stages 2 and 3 read the class (Thach).**
  `diagnosis.json` went to `17.0` (`notes` and `suggested_classes`; stages
  read each line's class from cleaned.csv); `metrics.json` stays `16.0` (the
  migration's one major, taken in 2E-t1) and gains `core.identity`,
  `core.outside_revenue`, `core.unclassified`, `core.unmeasurable`,
  `core.notes` and `products.suggested_classes`; `undated_lines` leaves out
  the unmeasurable lines; `velocity` is null on every file (stock figures are
  not supported in v1). `forecast.json`'s `products_at_stockout_risk` became
  nullable with `products_at_stockout_risk_reason`, null in v1 - in place at
  `1.0`: no stage writes forecast.json yet. On the demo files every figure is
  identical; the differences are the ones the line taxonomy's anchor lists.
  Both of diagnosis.json's new fields are required. A note's sentence and
  figures are part of both contracts (`contracts/lines.py` refuses any
  other): changing one is a major bump. A metrics.json written
  between 2E-t1 and 2E-t2 (16.0 without the new blocks) is refused as
  stale ("re-analyse this run"): the migration's one major per contract
  (2E-t1's T1).
- 2026-09-28: **session 2E-t1, the line taxonomy's classifier (Thach).** The
  line-class enum gained `gift_card` (closed enums: a major bump), so the
  stage 1 contracts went to `4.0` and `metrics.json`, whose `non_product`
  rows carry it, to `16.0` - the one major of the line-taxonomy migration,
  held through 2E-t3 (no build between them is released). `cleaned.csv`
  gained `line_class`, `class_source` and `suggested_class` (section 5).
  Stages 2 and 3 do not read them yet (2E-t2); a confirmed gift card is left
  out of revenue as a fee is. The three demo runs, through the built stage 1:
  every figure identical, `columns_out` +3. Readers refuse `3.x` stage 1
  files and `15.x` metrics files ("re-upload the file", "re-analyse").
- 2026-09-28: **session 2E-o, the fifth run's answers (Thach).** `metrics.json`
  went to `15.0` (a file dated on each month's last day is month grain too, so
  another month is compared; a day-month-year date is found beside a dotted
  time or before its time) and `diagnosis.json` to `16.0` (rules 5 and 6 are
  ranked together, so the same data can name another cause - Kaggle 2024-12
  moves from seasonality T2 at 1.48x to B1 at 0.96x; a supported directional
  cause comes before the movements; P3 reads signed; a trust check may be
  `not_applicable` in a month-end file). The Online Retail II demo month
  2011-11 is unchanged in both states. Readers refuse `14.x` metrics and
  `15.x` diagnosis files.
- 2026-09-27: **session 2E-j, dates decided at stage 1 (Thach).**
  `profile.json` went to `1.1` (optional per-column `date_order`) and the
  stage 1 contracts to `3.1` (optional `confirmations.dates_day_first` and
  `cleaning_report.json`'s `date_order`; `schema_inference.json` kept in
  step, unchanged) - minor, readers unaffected. `metrics.json` went to
  `14.0` (`period.month_grain`, required; a date column read in the decided
  order; placeholder dates and days the order cannot hold undated; a
  month-grain file's last month compared) and `diagnosis.json` to `15.0`
  (`calendar.method` gained `not_applicable` with nullable expectations, a
  trust check's `status` gained `not_applicable`; in a month-grain file D1,
  T1 and R3 are not testable, and T2 and B1 read the months). Both demo files are ISO and
  unchanged. Readers refuse `13.x` metrics and `14.x` diagnosis files.
- 2026-09-27: **session 2E-i, one text reading for every stage (Thach).**
  `metrics.json` went to `13.0` and `diagnosis.json` to `14.0`: customers,
  order ids, categories and transaction types read what a reader sees (a
  trailing zero-width space no longer makes a second customer, order or
  category, and "IN" with one is still stock received), and a cell with
  nothing visible is blank in every column - so the same data can group
  differently. Both demo files are identical. Readers refuse `12.x` metrics
  and `13.x` diagnosis files ("re-analyse this run").
- 2026-09-27: **session 2E-n, the products' sales and one fit (Thach).**
  `diagnosis.json` went to `13.0`: breadth's `products_share_of_change` (and
  so the classification, R1 and the product-lens gate) reads the products'
  SALE lines - customer returns are their own class - so the same data can
  classify breadth and name the headline's cause differently; rule 6 ranks
  every cause by one fit, `max(0, 1 - |1 - share of the net change|)`
  (superseding 3E1's cap and 2E-m's tie rule), and names every cause of an
  exact tie, or with no nameable cause fitting the largest measured
  movement each way (direction and money only), both with `hypothesis_id`
  null; the headline prints
  only the share of the net change. Readers refuse `12.x` diagnosis files ("re-analyse this run").
- 2026-09-27: **session 2E-m, the headline's ranking (Thach).**
  `diagnosis.json` went to `12.0`: no field changed, but the same data can
  name a different cause (Online Retail II 2010-03: T1 under 11.0, R2 now) -
  a change of meaning, major. Rule 6 ranks every supported cause by its
  share of the NET change (superseding 3E1's per-lens share; among terms all
  past the change, the larger share decides), and the product-lens gate
  reads breadth's decision - the products' net change over the net change,
  one definition for breadth, R1 and the gate. Readers refuse `11.x`
  diagnosis files ("re-analyse this run").
- 2026-09-27: **session 2E-l, lines outside the products.**
  `schema_inference.json`, `plan_*.json` and `cleaning_report.json` went to
  `3.0`: the line-class enum gained `pooled`, and a line-class answer may be
  `product` (review cycle 1) - a closed enum widened, major.
  `metrics.json` to `12.0`: a charge is no order and no return line (orders,
  AOV, return rate, units), pooled items are sales never ranked.
  `diagnosis.json` to `11.0`: the returns lens gains `charges_prev` /
  `charges_cur` and the product lens loses 2E-d2's `non_product` term and
  gains `unidentified` (the lines with no product identity - neither SKU nor
  name, or pooled - out of L, N and X; review cycle 1), hypotheses P4 and P5
  join the catalog (ADR-0005 amendment; P5 `not_testable` with no charge
  classed), breadth gains `outside_products` and `products_share_of_change`,
  and headline rule 6 names a product-lens cause only when more than half of
  the change sits in the product lens. Readers refuse `2.x`
  stage 1 files ("re-upload"), `11.x` metrics and `10.x` diagnosis files
  ("re-analyse this run").
- 2026-09-26: **session 2E-d2, lines that are not products.**
  `schema_inference.json` (`non_product_candidates`), `plan_*.json` and
  `cleaning_report.json` (`confirmations.line_classes`) went to `2.3` -
  optional fields, minor; `metrics.json` to `11.0` (`core.non_product`
  required; fees and adjustments leave revenue, a discount is no return line,
  classed lines leave the product tables) and `diagnosis.json` to `10.0`
  (`tree.products.non_product` required: the lens's six terms sum to the
  change in gross sales; the `(not a product)` member). Readers refuse `10.x`
  metrics and `9.x` diagnosis files with "re-analyse this run".
- 2026-09-26: **session 2E-k, walk-in placeholders.** `schema_inference.json`
  (`customer_placeholders`, `order_id_date_only`), `plan_*.json` and
  `cleaning_report.json` (`confirmations.customer_placeholders`) went to `2.2`
  - optional fields, minor; `metrics.json` to `10.0` and `diagnosis.json` to
  `9.0`: a confirmed placeholder has no customer (`customers.placeholder_lines`
  with its reason, required), and the order-id check is judged per receipt.
  The customer column is never imputed (AI_PIPELINE section 6). Readers
  refuse `9.x` metrics and `8.x` diagnosis files with "re-analyse this run".
- 2026-09-26: **session 2E-e2, the order basis decided in Review.**
  `plan_proposed.json` / `plan_final.json` and `cleaning_report.json` went to
  `2.1` (optional `confirmations`), `schema_inference.json` to `2.1`
  (optional `receipt_fill_lines`) - minor, readers unaffected;
  `metrics.json` to `9.0` and `diagnosis.json` to `8.0` (Thach's rule that a
  change of meaning is a major bump): an order id checked by date only counts
  only with the user's Yes, the customer fill stops at the user's No, and
  `customers.unfilled_receipt_lines` with its reason is required. Readers
  refuse `8.x` metrics and `7.x` diagnosis files with "re-analyse this run".
- 2026-09-26: **`metrics.json` went to `8.0` and `diagnosis.json` to `7.0`**
  (session 2E-h, Thach): every day and month is read on the wall clock as
  written (UTC before) with 1F's cell rule, `core.undated_lines` and its
  reason were added, and an order id with no sale line is judged on its
  counted lines. Readers refuse `7.x` metrics and `6.x` diagnosis files with
  "re-analyse this run".
- 2026-09-25: **`metrics.json` went to `7.0` and `diagnosis.json` to `6.0`**
  (session 2E-g, Thach): product keys and labels shared by both stages
  (`shared/products.py`), units sold on sale lines, the `(no product name)`
  gap never ranked (and never an R3 stockout or a D2 price-check product),
  a SKU-only line its product in stage 3 too, and `products.velocity` /
  `days_to_stockout` nullable with a reason when the file (or the product)
  has no stock-in line. Readers refuse `6.x` metrics and `5.x` diagnosis
  files with "re-analyse this run".
- 2026-09-25: **`metrics.json` went to `6.0` and `diagnosis.json` to `5.0`**
  (session 2E-f, Thach; a change of meaning is a major bump): the first day
  nets per product (`new_vs_returning`, the bridge's `new` and
  `resurrected`), exactly one order scores F = 1 (RFM segments), and a
  header-style receipt's unnamed lines are its named customer's (segment
  money, active customers, buyers, the bridge's terms and `unattributed`,
  the lever's customers). Readers refuse `5.x` metrics and `4.x` diagnosis
  files with "re-analyse this run". Stage 1 contracts are unchanged.
- 2026-09-24: **session 2E-e, the optional canonical field `order_id`.**
  `schema_inference.json`, `plan_proposed.json` / `plan_final.json` and
  `cleaning_report.json` went to `2.0` (the canonical enum gained `order_id`,
  the issue enum `order_id_not_one_order` - major by the enum rule above);
  `metrics.json` to `5.0` (orders are order ids when mapped, the required
  `orders_basis` and `orders_basis_reason`); `diagnosis.json` to `4.0` (the
  lever's orders and the B1/B2 statements follow the basis). `profile.json`
  stays `1.x`: it carries neither enum. Every reader refuses the older major
  with "re-upload" / "re-analyse".
- 2026-09-24: **`metrics.json` went to `4.0` and `diagnosis.json` to `3.0`**
  (session 2E-c2, Thach's rule that a change of meaning is a major bump): a
  return line needs a negative amount (`return_rate_*`), any return on a
  customer's first day means they are not new (`new_vs_returning`, the
  bridge's `new` and `resurrected`), and the segment "Returns only" is now
  "No purchases in file". Readers refuse `3.x` metrics and `2.x` diagnosis
  files with "re-analyse this run".
- 2026-09-24: **`metrics.json` went to `3.0` and `diagnosis.json` to `2.0`**
  (session 2E-c, Thach). metrics.json: a sale row needs a positive amount, a
  new customer's history must not open with a refund, and RFM ties score
  alike, so `orders_*`, `buyers_*`, `aov_*`, `return_rate_*`,
  `new_vs_returning` and every RFM score changed MEANING while the schema did
  not. The version is a promise to every reader - stage 5, the frontend,
  anyone opening the file - and a 2.x and a 3.x file whose "orders" differ
  must not be compared silently; readers require `3.x`, and a `2.x` file is
  refused with "re-analyse this run". diagnosis.json: the returns lens gained
  the required `deductions_prev` / `deductions_cur`, and gross sales became
  the sale rows only; readers require `2.x`. No writer of diagnosis.json
  exists yet (session 3G), so no file on disk is stranded.
- 2026-09-24: **`metrics.json` went to `2.0`** (session 2E): a major bump under
  the rule above, because `orders_*`, `aov_*`, `return_rate_*` and RFM
  frequency changed meaning (an order is a sale row) and
  `revenue_change_pct`, `biggest_decliners`, each decliner's
  `revenue_change_pct`, `contribution_pct` and `customers_previous` became
  nullable, each with a `*_reason`; `period.previous_complete`,
  `previous_incomplete_reason` and each decliner's `revenue_change` were
  added. `metrics.json` files had been written since session 2D, so the
  in-place precedent did not apply. Every reader requires `2.x`: a `1.x` file
  is refused with "re-analyse this run" (`contracts/_base.py`'s
  per-contract `supported_major`), so stage 3 never reads old meanings
  silently. **Runs analysed before 2E keep their `1.0` `metrics.json` until
  re-analysed.** Every other contract file stays at `1.x`.
  `diagnosis.json` needed no bump for this: no endpoint or `__main__` writes
  it yet (that is session 3G) - confirmed by search, not assumed.
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

## 11. The consumer contract (Thach, 2026-09-29, session 3G0)

Stages 4 and 5 and the frontend read `metrics.json` and `diagnosis.json`
through the fields listed here, and no others (CLAUDE.md 3.7).
`tests/contracts/test_consumer_contract.py` reads these tables and fails if
a listed field is renamed, removed, or changes type - its constraints (a
range, the `YYYY-MM` format) and its JSON key included - or if a vocabulary
below differs from the code's. The rows and vocabularies as first written
are frozen (`tests/contracts/consumer_fields_v1.json`), so **these fields
change only additively**: a new field is a new row; an enum or a vocabulary
may gain a value - still a major bump when a reader validates it closed
(section 10), with every consumer updated in the same session - never lose
one. A field not listed follows section 10 alone, and no consumer reads it
until its row is added (section 10: "never let a stage read a field that is
not documented here").

Readers: **4A** the forecast (the revenue series and the period); **4B**
the strategy step's AI input (`docs/AI_PIPELINE.md` section 8): built from
the 4B rows only, never the whole file, each list capped; **5** the report
(stage 5: `report.json`, `report.html`); **FE** the frontend's Insights
page (Phase 6, through the API answers that carry these files).

How the fields are read:
- **Notes by code** (Thach, adjustments 1 and 2): a note is read by its
  `code`, `figures` and `measures` - the measure names are a closed
  vocabulary per code (below; checked on read) - and `always_on` (written
  from `contracts.lines.is_always_on`: `discounts_in_prices`, and
  `same_day_cancellations` whose every measure counts 0 lines) says where
  it is shown: once, in "How to read these figures", when true; beside
  each figure its `figures` name otherwise. The file's `text` is NOT a
  consumer field: a consumer words a note by its code - stage 5 and 4B's
  input from `contracts.lines.NOTE_TEXTS`, the frontend with its own copy
  per code.
- **Sentences written by code** - every `*_reason`, `non_product[].reason`,
  `trust.checks[].message`, `trust.limitations`, `hypotheses[].statement`
  and `.rule`, `not_testable[].statement` and `.reason`, `headline.message`
  - are shown as written and never parsed; a consumer decides on the codes
  and vocabularies beside them (`headline.rule`, `hypotheses[].id` and
  `.verdict`, `trust.verdict`, `signals[].signal`, a segment's name).
  `hypotheses[].evidence` is shown key by key as it stands (its keys are
  free-form per hypothesis; none is relied on).
- **An incomplete previous month is never compared** (CONTRACTS 6): when
  `period.previous_complete` is false, a consumer shows the current
  month's figures and `previous_incomplete_reason`, never a previous
  value beside a current one, a change, or an arrow - metrics.json keeps
  the previous values (the identity needs them), but they describe part
  of a month.
- **No consumer computes a figure** (CLAUDE.md 3.2; section 9: "stage 5
  performs no analysis"): the one change metrics.json carries is
  `revenue_change_pct` (null with its reason). Every other KPI is shown as
  its two months' values side by side; a consumer that needs another
  change (orders, AOV, the return rate in points) adds it to stage 2 as a
  new field first. Stage 5 shows stage 3's trust badge beside stage 2's
  period-over-period KPIs (CONTRACTS 6).
- **Zeros that are not counts, and a partly covered month** (5A reviews 2
  #1, 2 #5, 3 #1, 4 #2; the standing rule): stage 2 writes 0 for a current
  month in which no line counted in revenue is dated, and 0 active
  customers for a month whose lines name nobody; and it takes a month the
  file starts inside as a whole current month. Stage 5 withholds the first
  two with their reasons and notes the third (`current_note`) - section 9.
  The frontend shows the same, and reads them from report.json's layer 1
  rather than deriving them again from these fields (one copy of the rule:
  Phase 6 wires it).
- **Months**: `revenue_by_month` holds every month with a dated counted
  line, a partial first and last month included. Which are complete is
  read from `period` (`data_start`, `data_end`, `month_grain`) by the one
  definition stage 3's history uses, `shared/periods.complete_months` (4A:
  no new stage 2 field - periods are frozen), and never past
  `period.current`. Stage 5 and the frontend DRAW a month whole only when
  both definitions say so: for the compared month `period.previous_complete`
  must be true as well (5A reviews 1 #1, 2 #3) - a chart never claims more
  than the KPIs beside it, nor than stage 3's history and the forecast. (The
  two disagree only about a file starting one or two days into the compared
  month: the KPIs compare with it, the chart does not draw it - 8D.) There,
  a month between the first and the last with no line counted in revenue is
  shown as a gap with its reason (a closed month or missing data, which the
  file cannot tell apart), never as 0 and never joined across.
- **A note that names revenue stands beside the forecast too** (4A review 2
  #4, the standing rule): forecast.json carries no metrics notes - the
  forecast is built from `core.revenue_by_month`, so wherever stage 5 or
  the frontend shows the forecast, every metrics.json note whose `figures`
  include `revenue` and is not `always_on` is shown beside it, as beside
  the revenue it came from; and so are forecast.json's own `history_note`
  and `season_note` when not null.
- **The notes stand beside the recommendations too** (4B review 1 #10, the
  standing rule): the AI's recommendations cite the files' figures in free
  text, which no code maps back to a figure, so wherever stage 5 or the
  frontend shows `recommendations`, every note of metrics.json and
  diagnosis.json that is not `always_on` is shown beside them - by
  construction, not left to the AI's wording.
- **Signals describe; none is a verdict in v1** (ADR-0006, ADR-0007): never
  word one as normal or unusual - the AI of 4B included - and read `mode`
  before comparing two rows (money or counts on a `level` row, percentage
  points on a `yoy` row).
- **Stock is not supported in v1**: `products.velocity` is null and
  `velocity_reason` says why - show the reason, never a stock figure.
- **A null figure is a value**: it carries its reason; show the reason,
  never a zero. The line taxonomy's blocks write a zero as 0.0
  (`docs/LINE_TAXONOMY.md` section 3); other figures - stage 3's
  attribution terms - may carry `-0.0`: show it as 0.
- **Constraints held by a model validator** (a figure must be finite; two
  fields null together) are not in the types above: the contracts' and
  the stages' tests pin them (`tests/contracts/`,
  `tests/stages/diagnose/test_3glite_assemble.py` for diagnosis.json's
  finite figures), not this table.
- **The AI's text** (`ai_findings`, `model_used`) is null in degraded mode
  (`docs/AI_PIPELINE.md` section 9) and always rendered escaped (SPECS
  SEC-3).
- **Not in the contract**: `trust.checks[].evidence`, `calendar.evidence`,
  `tree.customers.evidence` and `.previous_transition`, `tree.lever.reasons`,
  `buyers_*`, the stage 3 frame's history bounds, a
  dimension's filter flags - a consumer that needs one adds its row first.

#### metrics.json

| Field | Type | Read by |
|---|---|---|
| `schema_version` | `str` | 5 |
| `generated_at` | `AwareDatetime` | 5 |
| `period` | `object` | 4A, 4B, 5, FE |
| `period.current` | `str (YYYY-MM)` | 4A, 4B, 5, FE |
| `period.previous` | `str (YYYY-MM)` | 4A, 4B, 5, FE |
| `period.data_start` | `date` | 4A, 4B, 5, FE |
| `period.data_end` | `date` | 4A, 4B, 5, FE |
| `period.previous_complete` | `bool` | 4A, 4B, 5, FE |
| `period.previous_incomplete_reason` | `str \| None` | 4B, 5, FE |
| `period.month_grain` | `bool` | 4A, 4B, 5, FE |
| `core` | `object` | 4A, 4B, 5, FE |
| `core.revenue_current` | `float` | 4B, 5, FE |
| `core.revenue_previous` | `float` | 4B, 5, FE |
| `core.revenue_change_pct` | `float \| None` | 4B, 5, FE |
| `core.revenue_change_pct_reason` | `str \| None` | 4B, 5, FE |
| `core.orders_basis` | `Literal['order_id', 'lines']` | 4B, 5, FE |
| `core.orders_basis_reason` | `str \| None` | 4B, 5, FE |
| `core.orders_current` | `int (ge=0)` | 4B, 5, FE |
| `core.orders_previous` | `int (ge=0)` | 4B, 5, FE |
| `core.active_customers_current` | `int (ge=0)` | 4B, 5, FE |
| `core.active_customers_previous` | `int (ge=0)` | 4B, 5, FE |
| `core.aov_current` | `float \| None` | 4B, 5, FE |
| `core.aov_current_reason` | `str \| None` | 4B, 5, FE |
| `core.aov_previous` | `float \| None` | 4B, 5, FE |
| `core.aov_previous_reason` | `str \| None` | 4B, 5, FE |
| `core.return_rate_current` | `float (ge=0) \| None` | 4B, 5, FE |
| `core.return_rate_current_reason` | `str \| None` | 4B, 5, FE |
| `core.return_rate_previous` | `float (ge=0) \| None` | 4B, 5, FE |
| `core.return_rate_previous_reason` | `str \| None` | 4B, 5, FE |
| `core.revenue_by_month` | `list[object]` | 4A, 4B, 5, FE |
| `core.revenue_by_month[].period` | `str (YYYY-MM)` | 4A, 4B, 5, FE |
| `core.revenue_by_month[].revenue` | `float` | 4A, 4B, 5, FE |
| `core.undated_lines` | `int (ge=0)` | 4B, 5, FE |
| `core.undated_lines_reason` | `str \| None` | 4B, 5, FE |
| `core.non_product` | `list[object]` | 4B, 5, FE |
| `core.non_product[].line_class` | `Literal['charge', 'discount', 'pooled', 'cost', 'adjustment', 'gift_card']` | 4B, 5, FE |
| `core.non_product[].lines` | `int (gt=0)` | 4B, 5, FE |
| `core.non_product[].amount` | `float` | 4B, 5, FE |
| `core.non_product[].amount_current` | `float` | 4B, 5, FE |
| `core.non_product[].amount_previous` | `float` | 4B, 5, FE |
| `core.non_product[].reason` | `str` | 4B, 5, FE |
| `core.identity` | `object` | 4B, 5, FE |
| `core.identity.current` | `object` | 4B, 5, FE |
| `core.identity.current.gross_sales` | `float` | 4B, 5, FE |
| `core.identity.current.returns` | `float` | 4B, 5, FE |
| `core.identity.current.discounts` | `float` | 4B, 5, FE |
| `core.identity.current.other_deductions` | `float` | 4B, 5, FE |
| `core.identity.current.other_revenue` | `float` | 4B, 5, FE |
| `core.identity.current.net_revenue` | `float` | 4B, 5, FE |
| `core.identity.current.returns_on_suggested_keys` | `float` | 4B, 5, FE |
| `core.identity.current.money_moved` | `float (ge=0)` | 4B, 5, FE |
| `core.identity.previous` | `object` | 4B, 5, FE |
| `core.identity.previous.gross_sales` | `float` | 4B, 5, FE |
| `core.identity.previous.returns` | `float` | 4B, 5, FE |
| `core.identity.previous.discounts` | `float` | 4B, 5, FE |
| `core.identity.previous.other_deductions` | `float` | 4B, 5, FE |
| `core.identity.previous.other_revenue` | `float` | 4B, 5, FE |
| `core.identity.previous.net_revenue` | `float` | 4B, 5, FE |
| `core.identity.previous.returns_on_suggested_keys` | `float` | 4B, 5, FE |
| `core.identity.previous.money_moved` | `float (ge=0)` | 4B, 5, FE |
| `core.outside_revenue` | `list[object]` | 4B, 5, FE |
| `core.outside_revenue[].line_class` | `Literal['sale', 'pooled_sale', 'customer_return', 'pooled_return', 'allowance', 'pooled_allowance', 'discount', 'charge', 'no_money', 'pooled_no_money', 'gift_card_sale', 'gift_card_redemption', 'cost', 'adjustment', 'stock_in', 'unclassified', 'unmeasurable']` | 4B, 5, FE |
| `core.outside_revenue[].scope` | `Literal['file', 'current', 'previous']` | 4B, 5, FE |
| `core.outside_revenue[].sign` | `Literal['positive', 'negative', 'no_money'] \| None` | 4B, 5, FE |
| `core.outside_revenue[].lines` | `int (gt=0)` | 4B, 5, FE |
| `core.outside_revenue[].amount` | `float (finite)` | 4B, 5, FE |
| `core.outside_revenue[].lines_without_amount` | `int (ge=0)` | 4B, 5, FE |
| `core.unclassified` | `object` | 4B, 5, FE |
| `core.unclassified.lines` | `int (ge=0)` | 4B, 5, FE |
| `core.unclassified.amount` | `float (finite)` | 4B, 5, FE |
| `core.unclassified.share_of_money_moved` | `float (finite) \| None` | 4B, 5, FE |
| `core.unmeasurable` | `list[object]` | 4B, 5, FE |
| `core.unmeasurable[].scope` | `Literal['file', 'current', 'previous']` | 4B, 5, FE |
| `core.unmeasurable[].reason` | `Literal['no quantity', 'no price', 'amount too large to add']` | 4B, 5, FE |
| `core.unmeasurable[].lines` | `int (gt=0)` | 4B, 5, FE |
| `core.notes` | `list[object] (one_per_code)` | 4B, 5, FE |
| `core.notes[].code` | `Literal['same_day_cancellations', 'returns_booked_as_in', 'unconfirmed_suggestions', 'unconfirmed_deductions', 'discounts_in_prices', 'other_transaction_types']` | 4B, 5, FE |
| `core.notes[].figures` | `list[Literal['revenue', 'gross_sales', 'returns', 'discounts', 'other_deductions', 'return_rate', 'orders', 'aov', 'units', 'customers', 'products', 'diagnosis']]` | 4B, 5, FE |
| `core.notes[].measures` | `list[object]` | 4B, 5, FE |
| `core.notes[].measures[].name` | `str (min_length=1)` | 4B, 5, FE |
| `core.notes[].measures[].scope` | `Literal['file', 'current', 'previous']` | 4B, 5, FE |
| `core.notes[].measures[].lines` | `int (ge=0)` | 4B, 5, FE |
| `core.notes[].measures[].amount` | `float (finite) \| None` | 4B, 5, FE |
| `core.notes[].measures[].orders` | `int (ge=0) \| None` | 4B, 5, FE |
| `core.notes[].measures[].keys` | `int (ge=0) \| None` | 4B, 5, FE |
| `core.notes[].always_on` | `bool` | 4B, 5, FE |
| `customers` | `object` | 4B, 5, FE |
| `customers.rfm_reference_date` | `date` | 4B, 5, FE |
| `customers.segments` | `list[object]` | 4B, 5, FE |
| `customers.segments[].segment` | `str` | 4B, 5, FE |
| `customers.segments[].customers` | `int (ge=0)` | 4B, 5, FE |
| `customers.segments[].revenue_share_pct` | `float \| None` | 4B, 5, FE |
| `customers.segments[].avg_monetary` | `float` | 4B, 5, FE |
| `customers.segments[].customers_previous` | `int (ge=0) \| None` | 4B, 5, FE |
| `customers.new_vs_returning` | `object` | 4B, 5, FE |
| `customers.new_vs_returning.new_customers` | `int (ge=0)` | 4B, 5, FE |
| `customers.new_vs_returning.returning_customers` | `int (ge=0)` | 4B, 5, FE |
| `customers.new_vs_returning.new_revenue` | `float` | 4B, 5, FE |
| `customers.new_vs_returning.returning_revenue` | `float` | 4B, 5, FE |
| `customers.customers_previous_reason` | `str \| None` | 4B, 5, FE |
| `customers.revenue_share_reason` | `str \| None` | 4B, 5, FE |
| `customers.unfilled_receipt_lines` | `int (ge=0)` | 4B, 5, FE |
| `customers.unfilled_receipt_lines_reason` | `str \| None` | 4B, 5, FE |
| `customers.placeholder_lines` | `int (ge=0)` | 4B, 5, FE |
| `customers.placeholder_lines_reason` | `str \| None` | 4B, 5, FE |
| `products` | `object` | 4B, 5, FE |
| `products.pareto` | `object` | 4B, 5, FE |
| `products.pareto.products_for_80pct_revenue` | `int (ge=0)` | 4B, 5, FE |
| `products.pareto.total_products` | `int (ge=0)` | 4B, 5, FE |
| `products.pareto.concentration_pct` | `float (ge=0, le=100) \| None` | 4B, 5, FE |
| `products.pareto.concentration_reason` | `str \| None` | 4B, 5, FE |
| `products.top_products` | `list[object]` | 4B, 5, FE |
| `products.top_products[].product` | `str` | 4B, 5, FE |
| `products.top_products[].revenue` | `float` | 4B, 5, FE |
| `products.top_products[].units` | `int` | 4B, 5, FE |
| `products.biggest_decliners` | `list[object] \| None` | 4B, 5, FE |
| `products.biggest_decliners[].product` | `str` | 4B, 5, FE |
| `products.biggest_decliners[].revenue_change` | `float` | 4B, 5, FE |
| `products.biggest_decliners[].revenue_change_pct` | `float \| None` | 4B, 5, FE |
| `products.biggest_decliners[].revenue_change_pct_reason` | `str \| None` | 4B, 5, FE |
| `products.biggest_decliners_reason` | `str \| None` | 4B, 5, FE |
| `products.velocity` | `list[object] \| None` | 5, FE |
| `products.velocity_reason` | `str \| None` | 5, FE |
| `products.suggested_classes` | `dict[str, Literal['charge', 'discount', 'pooled', 'cost', 'adjustment', 'gift_card']]` | 4B, 5, FE |
| `by_dimension` | `object` | 4B, 5, FE |
| `by_dimension.country` | `list[object]` | 4B, 5, FE |
| `by_dimension.country[].name` | `str` | 4B, 5, FE |
| `by_dimension.country[].revenue_current` | `float` | 4B, 5, FE |
| `by_dimension.country[].revenue_previous` | `float` | 4B, 5, FE |
| `by_dimension.country[].contribution_pct` | `float \| None` | 4B, 5, FE |
| `by_dimension.category` | `list[object]` | 4B, 5, FE |
| `by_dimension.category[].name` | `str` | 4B, 5, FE |
| `by_dimension.category[].revenue_current` | `float` | 4B, 5, FE |
| `by_dimension.category[].revenue_previous` | `float` | 4B, 5, FE |
| `by_dimension.category[].contribution_pct` | `float \| None` | 4B, 5, FE |
| `by_dimension.contribution_reason` | `str \| None` | 4B, 5, FE |

#### diagnosis.json

| Field | Type | Read by |
|---|---|---|
| `schema_version` | `str` | 5 |
| `generated_at` | `AwareDatetime` | 5 |
| `model_used` | `str \| None` | 4B, 5, FE |
| `frame` | `object` | 4B, 5, FE |
| `frame.current` | `str (YYYY-MM)` | 4B, 5, FE |
| `frame.previous` | `str (YYYY-MM)` | 4B, 5, FE |
| `frame.year_ago_current` | `str (YYYY-MM) \| None` | 4B, 5, FE |
| `frame.year_ago_previous` | `str (YYYY-MM) \| None` | 4B, 5, FE |
| `frame.history_months` | `int (ge=0)` | 4B, 5, FE |
| `trust` | `object` | 4B, 5, FE |
| `trust.verdict` | `Literal['trusted', 'caution', 'blocked']` | 4B, 5, FE |
| `trust.checks` | `list[object]` | 4B, 5, FE |
| `trust.checks[].id` | `Literal['D1', 'D2', 'D3']` | 4B, 5, FE |
| `trust.checks[].status` | `Literal['ok', 'caution', 'blocked', 'inconclusive', 'not_applicable']` | 4B, 5, FE |
| `trust.checks[].message` | `str` | 4B, 5, FE |
| `trust.limitations` | `list[str]` | 4B, 5, FE |
| `calendar` | `object \| None` | 4B, 5, FE |
| `calendar.method` | `Literal['weekday_weights', 'day_count', 'not_applicable']` | 4B, 5, FE |
| `calendar.expected_cur` | `float \| None` | 4B, 5, FE |
| `calendar.expected_prev` | `float \| None` | 4B, 5, FE |
| `calendar.calendar_effect` | `float` | 4B, 5, FE |
| `calendar.calendar_adjusted_change` | `float` | 4B, 5, FE |
| `signals` | `list[object] \| None` | 4B, 5, FE |
| `signals[].series` | `Literal['revenue', 'orders', 'active_customers', 'frequency', 'aov', 'units_per_order', 'price_per_unit', 'return_rate']` | 4B, 5, FE |
| `signals[].mode` | `Literal['level', 'yoy']` | 4B, 5, FE |
| `signals[].value_cur` | `float \| None` | 4B, 5, FE |
| `signals[].center` | `float \| None` | 4B, 5, FE |
| `signals[].lower` | `float \| None` | 4B, 5, FE |
| `signals[].upper` | `float \| None` | 4B, 5, FE |
| `signals[].signal` | `Literal['above', 'below', 'within', 'insufficient_history']` | 4B, 5, FE |
| `signals[].rule` | `Literal[1, 2] \| None` | 4B, 5, FE |
| `signals[].mode_fallback` | `Literal['no_year_ago_value', 'unusable_year_ago_base'] \| None` | 4B, 5, FE |
| `signals[].insufficient_reason` | `Literal['too_few_points', 'no_current_value', 'no_measurable_spread'] \| None` | 4B, 5, FE |
| `signals[].limits_method` | `Literal['median_moving_range', 'mean_moving_range', 'minimum_spread']` | 5, FE |
| `tree` | `object \| None` | 4B, 5, FE |
| `tree.method` | `Literal['shapley']` | 4B, 5, FE |
| `tree.lever` | `object` | 4B, 5, FE |
| `tree.lever.level1` | `object \| None` | 4B, 5, FE |
| `tree.lever.level1.formula` | `Literal['customers*frequency*aov', 'orders*aov', 'units_per_order*price_per_unit']` | 4B, 5, FE |
| `tree.lever.level1.factors` | `list[object]` | 4B, 5, FE |
| `tree.lever.level1.factors[].name` | `Literal['customers', 'frequency', 'orders', 'aov', 'units_per_order', 'price_per_unit']` | 4B, 5, FE |
| `tree.lever.level1.factors[].value_prev` | `float` | 4B, 5, FE |
| `tree.lever.level1.factors[].value_cur` | `float` | 4B, 5, FE |
| `tree.lever.level1.factors[].contribution` | `float` | 4B, 5, FE |
| `tree.lever.level2` | `object \| None` | 4B, 5, FE |
| `tree.lever.level2.formula` | `Literal['customers*frequency*aov', 'orders*aov', 'units_per_order*price_per_unit']` | 4B, 5, FE |
| `tree.lever.level2.factors` | `list[object]` | 4B, 5, FE |
| `tree.lever.level2.factors[].name` | `Literal['customers', 'frequency', 'orders', 'aov', 'units_per_order', 'price_per_unit']` | 4B, 5, FE |
| `tree.lever.level2.factors[].value_prev` | `float` | 4B, 5, FE |
| `tree.lever.level2.factors[].value_cur` | `float` | 4B, 5, FE |
| `tree.lever.level2.factors[].contribution` | `float` | 4B, 5, FE |
| `tree.lever.gross_to_net` | `float \| None` | 4B, 5, FE |
| `tree.lever.masked_shift_alert` | `bool \| None` | 4B, 5, FE |
| `tree.lever.masked_shift_pair` | `object \| None` | 4B, 5, FE |
| `tree.lever.masked_shift_pair.formula` | `Literal['customers*frequency*aov', 'orders*aov', 'units_per_order*price_per_unit']` | 4B, 5, FE |
| `tree.lever.masked_shift_pair.factors` | `list[object]` | 4B, 5, FE |
| `tree.lever.masked_shift_pair.factors[].name` | `Literal['customers', 'frequency', 'orders', 'aov', 'units_per_order', 'price_per_unit']` | 4B, 5, FE |
| `tree.lever.masked_shift_pair.factors[].value_prev` | `float` | 4B, 5, FE |
| `tree.lever.masked_shift_pair.factors[].value_cur` | `float` | 4B, 5, FE |
| `tree.lever.masked_shift_pair.factors[].contribution` | `float` | 4B, 5, FE |
| `tree.customers` | `object \| None` | 4B, 5, FE |
| `tree.customers.new` | `float` | 4B, 5, FE |
| `tree.customers.resurrected` | `float` | 4B, 5, FE |
| `tree.customers.expansion` | `float` | 4B, 5, FE |
| `tree.customers.contraction` | `float` | 4B, 5, FE |
| `tree.customers.lapsed` | `float` | 4B, 5, FE |
| `tree.customers.unattributed` | `float` | 4B, 5, FE |
| `tree.returns` | `object` | 4B, 5, FE |
| `tree.returns.gross_prev` | `float` | 4B, 5, FE |
| `tree.returns.gross_cur` | `float` | 4B, 5, FE |
| `tree.returns.returns_prev` | `float` | 4B, 5, FE |
| `tree.returns.returns_cur` | `float` | 4B, 5, FE |
| `tree.returns.deductions_prev` | `float` | 4B, 5, FE |
| `tree.returns.deductions_cur` | `float` | 4B, 5, FE |
| `tree.returns.charges_prev` | `float` | 4B, 5, FE |
| `tree.returns.charges_cur` | `float` | 4B, 5, FE |
| `tree.products` | `object` | 4B, 5, FE |
| `tree.products.volume` | `float` | 4B, 5, FE |
| `tree.products.mix` | `float` | 4B, 5, FE |
| `tree.products.price` | `float` | 4B, 5, FE |
| `tree.products.new_products` | `float` | 4B, 5, FE |
| `tree.products.discontinued_products` | `float` | 4B, 5, FE |
| `tree.products.unidentified` | `float` | 4B, 5, FE |
| `localization` | `object \| None` | 4B, 5, FE |
| `localization.dimensions` | `list[object]` | 4B, 5, FE |
| `localization.dimensions[].name` | `str` | 4B, 5, FE |
| `localization.dimensions[].members` | `list[object]` | 4B, 5, FE |
| `localization.dimensions[].members[].name` | `str` | 4B, 5, FE |
| `localization.dimensions[].members[].rev_prev` | `float` | 4B, 5, FE |
| `localization.dimensions[].members[].rev_cur` | `float` | 4B, 5, FE |
| `localization.dimensions[].members[].delta` | `float` | 4B, 5, FE |
| `localization.dimensions[].members[].share_of_change` | `float` | 4B, 5, FE |
| `localization.dimensions[].members[].is_data_gap` | `bool` | 4B, 5, FE |
| `localization.dimensions[].members[].is_not_a_product` | `bool` | 4B, 5, FE |
| `localization.dimensions[].other` | `object \| None` | 4B, 5, FE |
| `localization.dimensions[].other.name` | `str` | 4B, 5, FE |
| `localization.dimensions[].other.rev_prev` | `float` | 4B, 5, FE |
| `localization.dimensions[].other.rev_cur` | `float` | 4B, 5, FE |
| `localization.dimensions[].other.delta` | `float` | 4B, 5, FE |
| `localization.dimensions[].other.share_of_change` | `float` | 4B, 5, FE |
| `localization.dimensions[].other.is_data_gap` | `bool` | 4B, 5, FE |
| `localization.dimensions[].other.is_not_a_product` | `bool` | 4B, 5, FE |
| `localization.dimensions[].new_members` | `list[str]` | 4B, 5, FE |
| `localization.dimensions[].removed_members` | `list[str]` | 4B, 5, FE |
| `localization.mix_rate` | `object \| None` | 4B, 5, FE |
| `localization.mix_rate.metric` | `Literal['aov', 'price_per_unit']` | 4B, 5, FE |
| `localization.mix_rate.mix` | `float` | 4B, 5, FE |
| `localization.mix_rate.rate` | `float` | 4B, 5, FE |
| `localization.breadth` | `object` | 4B, 5, FE |
| `localization.breadth.declining_base_share` | `float (ge=0, le=1)` | 4B, 5, FE |
| `localization.breadth.top_member_share` | `float (ge=0, le=1)` | 4B, 5, FE |
| `localization.breadth.classification` | `Literal['broad', 'mixed', 'concentrated', 'outside_products']` | 4B, 5, FE |
| `localization.breadth.products_share_of_change` | `float \| None` | 4B, 5, FE |
| `hypotheses` | `list[object]` | 4B, 5, FE |
| `hypotheses[].id` | `str` | 4B, 5, FE |
| `hypotheses[].family` | `str` | 4B, 5, FE |
| `hypotheses[].lens` | `str` | 4B, 5, FE |
| `hypotheses[].statement` | `str` | 4B, 5, FE |
| `hypotheses[].verdict` | `Literal['supported', 'partial', 'ruled_out', 'inconclusive', 'not_testable']` | 4B, 5, FE |
| `hypotheses[].contribution` | `float \| None` | 4B, 5, FE |
| `hypotheses[].share` | `float \| None` | 4B, 5, FE |
| `hypotheses[].evidence` | `dict[str, Any]` | 5, FE |
| `hypotheses[].rule` | `str` | 4B, 5, FE |
| `not_testable` | `list[object]` | 4B, 5, FE |
| `not_testable[].id` | `str` | 4B, 5, FE |
| `not_testable[].statement` | `str` | 4B, 5, FE |
| `not_testable[].reason` | `str` | 4B, 5, FE |
| `headline` | `object` | 4B, 5, FE |
| `headline.rule` | `Literal[1, 2, 3, 4, 5, 6, 7]` | 4B, 5, FE |
| `headline.hypothesis_id` | `str \| None` | 4B, 5, FE |
| `headline.lens` | `str \| None` | 4B, 5, FE |
| `headline.message` | `str` | 4B, 5, FE |
| `ai_findings` | `object \| None` | 5, FE |
| `ai_findings.summary` | `str` | 5, FE |
| `ai_findings.headline_explanation` | `str` | 5, FE |
| `ai_findings.hypothesis_notes` | `list[object]` | 5, FE |
| `ai_findings.hypothesis_notes[].id` | `str` | 5, FE |
| `ai_findings.hypothesis_notes[].text` | `str` | 5, FE |
| `ai_findings.not_tested_note` | `str` | 5, FE |
| `notes` | `list[object] (one_per_code)` | 4B, 5, FE |
| `notes[].code` | `Literal['same_day_cancellations', 'returns_booked_as_in', 'unconfirmed_suggestions', 'unconfirmed_deductions', 'discounts_in_prices', 'other_transaction_types']` | 4B, 5, FE |
| `notes[].figures` | `list[Literal['revenue', 'gross_sales', 'returns', 'discounts', 'other_deductions', 'return_rate', 'orders', 'aov', 'units', 'customers', 'products', 'diagnosis']]` | 4B, 5, FE |
| `notes[].measures` | `list[object]` | 4B, 5, FE |
| `notes[].measures[].name` | `str (min_length=1)` | 4B, 5, FE |
| `notes[].measures[].scope` | `Literal['file', 'current', 'previous']` | 4B, 5, FE |
| `notes[].measures[].lines` | `int (ge=0)` | 4B, 5, FE |
| `notes[].measures[].amount` | `float (finite) \| None` | 4B, 5, FE |
| `notes[].measures[].orders` | `int (ge=0) \| None` | 4B, 5, FE |
| `notes[].measures[].keys` | `int (ge=0) \| None` | 4B, 5, FE |
| `notes[].always_on` | `bool` | 4B, 5, FE |
| `suggested_classes` | `dict[str, Literal['charge', 'discount', 'pooled', 'cost', 'adjustment', 'gift_card']]` | 4B, 5, FE |

#### Vocabularies

The closed vocabularies consumers decide on (the test compares them with the code).

| Vocabulary | Values |
|---|---|
| `hypothesis id` | `B1`, `B2`, `C1`, `C2`, `C3`, `C4`, `D1`, `D2`, `D3`, `P1`, `P2`, `P3`, `P4`, `P5`, `R1`, `R2`, `R3`, `T1`, `T2`, `T3` |
| `measure of discounts_in_prices` | - |
| `measure of other_transaction_types` | `(the file's own values)` |
| `measure of returns_booked_as_in` | `negative`, `positive`, `unknown`, `zero` |
| `measure of same_day_cancellations` | `returns`, `returns_unchecked`, `sales` |
| `measure of unconfirmed_deductions` | `lines` |
| `measure of unconfirmed_suggestions` | `lines`, `returns` |
| `not-testable id` | `X1`, `X2`, `X3`, `X4`, `X5`, `X6`, `X7` |
| `segment` | `At-risk`, `Champions`, `Hibernating`, `Loyal`, `Needs Attention`, `New`, `No purchases in file` |
