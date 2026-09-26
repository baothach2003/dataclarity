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
(stripped and case-folded: "Guest Customer", "Cash Sale", "Walk-In Client",
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
(adjust, adjustment, bad debt, manual, write-off, "dieu chinh"), discount
(discount, coupon, "giam gia", "chiet khau"), charge (postage, shipping,
delivery, carriage, freight, p&p, "phi van chuyen", "phi ship"), cost (fee,
bank charge, commission; not the Vietnamese "hoa hong", which is also roses),
and "sample" with no suggestion - and
its counted lines move money. Measured on Online Retail II: "carriage"
inside a name was four real products (FRENCH CARRIAGE LANTERN, BAROQUE
CARRIAGE CLOCK), so first-or-last; 13 keys are asked, among them C2
"CARRIAGE" and 23444 "Next Day Carriage", which a scan of digit-free codes
had missed. `positive` and `negative` sum the counted lines' amounts by sign
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
  "line_class": "charge" | "discount" | "cost" | "adjustment"}`, the value as
  written (stages compare it as they compare products; a `sku` answer does
  not class a line without a SKU). Unanswered, or "a product", a key is not
  listed and its lines stay products. Sent only when there are some; an
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
                    "customer_on_first_line_only": null}
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
  "schema_version": "10.0", "generated_at": "...",
  "period": {"current": "2011-11", "previous": "2011-10",
             "data_start": "2010-12-01", "data_end": "2011-12-09",
             "previous_complete": true, "previous_incomplete_reason": null},
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
    "velocity": [{"product": "...", "units_per_day": 12.4,
                  "days_to_stockout": 8.6, "days_to_stockout_reason": null}],
    "velocity_reason": null
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
  readable date (blank, or no date) - in no month and so in no figure - and
  `undated_lines_reason` says so; it is null exactly when the count is 0.
- **Lines the user classed as not products** (Thach, 2E-d2; plan
  `confirmations.line_classes`): a **charge** the customer paid (postage)
  stays in revenue and stays a sale or return line - orders, AOV, units and
  gross are unchanged - but is in no product table; a **discount** is a
  deduction (2E-c) whatever its signs - in revenue, no sale, no return, no
  units (a -1 @ +price discount was a return line, 2E-c2 item f); a **fee or
  cost** and an **accounting adjustment** are left out of revenue and of
  every figure as an "in" row is - no revenue, order, customer or product.
  No classed line is in a product table (top products, decliners, Pareto,
  velocity). **`core.non_product`** lists one row per class present (order
  charge, discount, cost, adjustment): its dated counted lines, their amount
  over the file and in the current and previous month, and a reason saying
  where the money went - an adjustment's amount is reported as a separate
  reconciling amount (Thach; not "the file's total minus the revenue shown",
  which fees, "in" rows and undated lines also make up - review F8). Empty
  when nothing is classed. The first-day netting keys every line as it
  would be keyed unanswered (`shared/products.netting_keys`): keyed as no
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
  (the zero-width joiners kept), spaces as one, case fully folded - for
  products ONLY: customers, categories, order ids and stage 1 read text as
  before 2E-g (Thach, option A), until one reading is decided for every
  stage. A line's product is its SKU,
  else its name (a name-only line takes the SKU when its name, on sale lines
  that have one, maps to exactly one SKU); a line with neither is the
  `(no product name)` data gap - in every total, in no table (top products,
  decliners, velocity, the Pareto count). A product's label is the name its
  sale lines carry most over the whole file, a tie going to the most recent
  sale, so it reads the same in both months; with no named sale line, the
  commonest name on any line, else the SKU; a name several products share
  shows each one's SKU ("BATHROOM METAL SIGN (21171)"). `top_products.units`
  and velocity's `units_per_day` count sale lines. **Velocity needs stock on
  hand**, derived from stock-in lines (transaction type "in", 2C) - which
  most POS exports do not have: floored at 0, both demo files read "0 days
  to stockout" for every product. A file with no stock-in line has
  `velocity` null with `velocity_reason`; in a file that has some, a product
  with none has `days_to_stockout` null with `days_to_stockout_reason`, and
  so does a product whose running balance (stock-in minus every counted
  line, day by day from the file's start) ever falls below zero: stock left
  before the file started is unknown. A stock-in line needs a date and a
  quantity, not a price.
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
`ai_findings`; step 8 is the only AI call and writes only `ai_findings`. Why
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
                "deductions_prev": 0.0, "deductions_cur": 0.0},
    "products": {"volume": -96000.0, "mix": -21000.0, "price": -8000.0,
                 "new_products": 12000.0, "discontinued_products": -27000.0,
                 "non_product": 0.0}
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
  }
}
```

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
`(uncategorised)`, `(no product name)`, `(no customer)`. The product
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
  `delta_net` (`delta_gross - delta_returns - delta_deductions`; gross is the
  sale rows, returns the return lines, deductions every other counted row -
  2E-c, `diagnosis.json` 2.0). A reader must not add shares across lenses, and stage 5 must not
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
  from net in-minus-out, and only when the file has stock-in lines (2E-g).
  Hypothesis R3 here is a *sales-gap* signal - it reads the sales pattern,
  never stock, so a sales-only file does not touch it - a product
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
