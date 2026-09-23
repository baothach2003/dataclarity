# DataClarity: Stage 3 Diagnostic Engine Design

**Status:** approved design input for the Stage 3 SPECS UPDATE session.
**Scope decided by Thach:** full engine, 7 sessions (not the reduced MVP).
**How to use this file:** it is the input document for the SPECS UPDATE session.
Once that session lands, `docs/CONTRACTS.md` (section 7), `docs/AI_PIPELINE.md`
(section 7) and `PROJECT_PLAN.md` (Phase 3) own the facts. This file then remains
the record of *why* the design looks the way it does (it can seed ADR-0004).
Where this file and those documents disagree after the SPECS UPDATE session,
those documents win.

---

## 1. Why the original Phase 3A plan was not enough

The original plan decomposed revenue into customers x frequency x AOV with
sequential substitution and let the AI choose which hypotheses to rule out.
Five concrete weaknesses, each verified numerically:

### 1.1 Sequential substitution is order-dependent

Changing the order in which factors are substituted changes each factor's
attribution. Computed on the Figma sample data (FIGMA_DESIGN_NOTES section 6,
revenue 104,160 -> 96,152):

| Order | Customers | Frequency | AOV |
|---|---|---|---|
| C -> F -> A (the Figma example) | -10,752 | +1,792 | +952 |
| F -> A -> C | -11,068 | +1,998 | +1,062 |
| Shapley (average of all 6 orders) | -10,910 | +1,904 | +997 |

With a larger swing (customers 1,000 -> 600, frequency 2.0 -> 2.4, AOV 50 -> 70,
revenue 100,000 -> 100,800) the spread becomes severe: the customers effect ranges
from -40,000 to -67,200 (68%) and the AOV effect from +24,000 to +48,000 (2x)
depending only on the order a developer picked. Shapley gives -53,067 / +18,933 /
+34,933, independent of order.

LMDI was considered and rejected: it is also exact, but it uses logarithms and
breaks when revenue is zero or negative, which DataClarity allows (returns are
negative-quantity rows since 2A).

### 1.2 A flat total can hide large offsetting movements

In the larger-swing example revenue moved +0.8% while the business lost 40% of its
customers, masked by AOV +40%. A diagnosis that only asks "did revenue move?"
misses the most dangerous case. The sum of absolute contributions divided by the
absolute net change (gross-to-net ratio) is 133.7 here.

### 1.3 AOV is too coarse, and Simpson's paradox hides in it

Two categories, A cheap (AOV 20 -> 22) and B expensive (AOV 100 -> 105). Both rose.
Order share moved from 50/50 to 80/20 towards A. Overall AOV fell 60 -> 38.6 (-36%).
Split: rate effect +3.05, mix effect -24.45 (sum exactly -21.4). A three-factor
report says "AOV fell 36%", which leads to a wrong action (discounts, upsell) when
the truth is a mix shift towards cheaper products.

### 1.4 No check of whether the change is real or unusual

Nothing distinguished a data gap, a calendar effect or routine noise from a real
business change.

### 1.5 The AI chose which hypotheses to test

`prompts/root_cause.md` asked the AI to rule out at least two hypotheses, but the
AI picked them. It could pick easy ones and skip the real cause. This violates the
spirit of ADR-0002: the AI must not decide what gets measured.

---

## 2. Principles (from practitioner and research sources)

1. **Multiple causes, measured as shares.** Business changes rarely have a single
   cause; causes act as a collection of upward and downward pressures. The engine
   reports how much of the change each cause explains, never "the" culprit.
2. **Data quality first.** Check for data issues before anything else; test whether
   a change is systemic across dimensions or localized; compare against correlated
   metrics (Sequoia, Analyzing Metric Changes).
3. **A fixed causal taxonomy.** Component drift, temporal variance, influence drift,
   dimension drift (value within a slice changes, slice proportions change, slices
   added or removed), event shocks (Levers Labs).
4. **Separate signal from noise before explaining.** Point-to-point comparisons
   create false alarms; natural process limits computed from the metric's own
   history separate routine from exceptional variation (Wheeler, XmR charts).
5. **Calendar effects are real in retail.** Months differ in length and in how many
   of each weekday they contain; Saturdays dominate retail sales (Statistics Canada,
   US Census Bureau).
6. **Customer growth accounting.** Revenue change = new + resurrected + expansion -
   contraction - churned (lapsed), an additive and exact identity (Tribe Capital /
   Social Capital).
7. **A fixed pipeline, no data-dependent slicing.** Choosing analyses after seeing
   the data inflates false discoveries (the garden of forking paths); Spotify
   standardizes its analysis pipeline partly for this reason. Hence the hypothesis
   catalog is fixed in advance and identical for every run.
8. **Contribution is not causation.** This is observational data. The engine
   reports decompositions and consistency with hypotheses, never proof of cause
   (Tableau Explain Data states the same limitation for its own feature).

---

## 3. Inputs and data availability

### 3.1 Inputs

- `runs/<id>/metrics.json` (Stage 2): period, core, customers, products, by_dimension.
- `runs/<id>/cleaned.csv` (Stage 1): row-level data, needed for units, customer
  flows, active days, product-level prices.
- `runs/<id>/cleaning_report.json` (Stage 1): column_mapping, warnings.

Stage 3 must NOT import `stages/analyze`. The transaction parsing logic currently
in `stages/analyze/metrics_core.py` (`ParsedTransactions`, `parse_transactions`,
`require_column`, `pct_change`, the blank-value helper) moves to `shared/` in
session 2 so both stages compute from one definition.

### 3.2 Canonical fields and degradation

| Field | Required? | Used for | If missing |
|---|---|---|---|
| transaction_date | yes | everything | stage cannot run (already enforced) |
| quantity | yes | units, returns, basket size | stage cannot run |
| unit_price | no | revenue | ANALYSIS_FAILED already at Stage 2 |
| product_name / sku | yes (product_name) | product lens, PVM, R1-R3 | n/a |
| category | no | category localization, category mix | category localization skipped; P2 uses product-level mix only |
| customer | no | customer count, frequency, customer bridge, C1-C4 | lever tree falls back to Orders x AOV; C1-C4 become `not_testable` |
| transaction_type | no | revenue scope | all rows treated as `out` (2A rule) |
| country | does not exist | n/a | listed as not testable |

### 3.3 Consistency requirement with Stage 2

Every figure Stage 3 recomputes from `cleaned.csv` that also exists in
`metrics.json` must match it exactly (revenue, orders, active customers per
period). A dedicated test enforces this. A mismatch means the two stages disagree
on definitions, which would make the report contradict itself.

---

## 4. Pipeline overview

| Step | Question | Output block |
|---|---|---|
| 1. Frame | What is compared with what? | `frame` |
| 2. Trust gate | Can the data be trusted? | `trust` (trusted / caution / blocked) |
| 3. Calendar | How much of the change is calendar only? | `calendar` |
| 4. Signal vs noise | Is the change unusual, for the total AND each component? | `signals` |
| 5. Metric tree | Which lever moved? | `tree` |
| 6. Localization | Where did it happen? | `localization` |
| 7. Hypotheses | Which fixed hypotheses hold? | `hypotheses`, `not_testable`, `headline` |
| 8. Narration (AI) | How is it said in words? | `ai_findings` |

Steps 1 to 7 are deterministic pandas. Only step 8 calls the AI.
If step 2 returns `blocked`, steps 3 to 6 are skipped and the headline reports the
data problem.

---

## 5. Step specifications

Notation: `cur` = current period, `prev` = previous period, both taken from
`metrics.json.period` (latest complete calendar month and the month before, per
2A). "Revenue-counted rows" follows 2A's scope (rows of type `in` excluded;
negative quantity rows are returns and stay in net revenue). An "order" follows
2A's definition exactly (reuse the shared helper, never redefine).

### 5.1 Step 1: Frame

- Comparison pair: `cur` vs `prev`.
- Year-ago pair: the same two calendar months one year earlier, if both exist in
  the data (needed by T2).
- History window: all complete months strictly before `cur`, at most the 24 most
  recent (used by steps 3 and 4).
- Output: `frame = {current, previous, year_ago_current?, year_ago_previous?,
  history_months, history_start, history_end}`.

### 5.2 Step 2: Trust gate

Three checks. Each produces `ok | caution | blocked` plus evidence.

**D1 coverage.** For each period compute `zero_days` = calendar days with no
revenue-counted rows. From the history window compute the store's normal
zero-day rate `z` (share of calendar days with no rows). Then
`excess_zero_days(cur) = max(0, zero_days(cur) - z * days_in_month(cur))`.

- `caution` if `excess_zero_days >= 3` or `>= 10%` of days in the month.
- `blocked` if `excess_zero_days >= 50%` of days in the month.
- Estimated revenue gap: `excess_zero_days * mean revenue per active day in prev`.

**D2 uniform price-level shift.** Take products sold in both periods with at
least 3 revenue-counted rows in each (require at least 20 such products, else
`inconclusive`). For each, `ratio = median unit_price(cur) / median unit_price(prev)`.
If at least 80% of ratios lie within +/-2% of their common median AND that common
median is outside [0.90, 1.10], return `caution` with the message: "uniform
price-level shift across X% of products; verify whether this is a unit or
currency change in the data or a deliberate repricing". Never `blocked`: the
engine cannot tell a data error from a real uniform repricing.

**D3 flagged-row concentration.** Share of rows carrying any `__flag_*` column set
to true, per period. `caution` if `share(cur) >= 2 * share(prev)` and
`share(cur) >= 2%`.

Known limitation, stated in the output: rows removed by `drop_rows_missing` in
Stage 1 are not in `cleaned.csv`, so their period is unknown. Fixing this needs a
Stage 1 contract change (dropped-row counts per month in `cleaning_report.json`);
it is in the Backlog, not in Phase 3.

Gate verdict: `blocked` if any check is blocked; else `caution` if any is caution;
else `trusted`.

### 5.3 Step 3: Calendar adjustment

- Requires at least 8 weeks of history; otherwise use day-count only
  (`method = "day_count"`), stated in the output.
- Weekday weights `w_d` (d = Monday..Sunday) = mean revenue per calendar date of
  weekday d over the history window, zero-revenue dates included (so regular
  closing days are reflected). Dates inside a D1 excess gap are excluded.
- Expected revenue of a month `E(m) = sum over d of count_d(m) * w_d`.
- `calendar_effect = revenue_prev * (E(cur) / E(prev) - 1)`.
- `calendar_adjusted_change = change_abs - calendar_effect`.
- Output: `calendar = {method, weights, expected_cur, expected_prev,
  calendar_effect, calendar_adjusted_change}`.

### 5.4 Step 4: Signal vs noise

Series (monthly, one value per complete month): revenue, orders, active customers
(if mapped), frequency, AOV, units per order, price per unit, return rate.

- **Mode.** If at least 25 complete months exist, use year-over-year % change
  series (removes seasonality); else use level series (`mode = "level"`).
- **Baseline.** Points before `cur` within the history window. If fewer than 8
  baseline points: `signal = "insufficient_history"` for that series.
- **XmR limits.** `center = mean(baseline)`,
  `mR_bar = mean(|x_t - x_(t-1)|)` over consecutive baseline points,
  `limits = center +/- 2.66 * mR_bar`.
- **Detection rules (deliberately few).** Rule 1: current point outside the
  limits. Rule 2: the current point and the 7 before it all on the same side of
  the center line. More rules create over-reaction.
- Output per series: `{mode, value_cur, center, lower, upper, signal:
  above | below | within | insufficient_history, rule}`.

The masked-shift alert is computed in step 5 because it needs the tree.

### 5.5 Step 5: Metric tree

All decompositions must reconcile exactly to their totals (relative tolerance
1e-9, enforced by tests).

**5.5.1 Shapley for a product of factors.** For `F = x_1 * x_2 * ... * x_n`, the
contribution of factor i is the average, over all n! orderings of the factors,
of the change in F when x_i switches from its `prev` value to its `cur` value
given the factors already switched earlier in that ordering. With n <= 3,
enumerate all orderings. The contributions sum exactly to `F(cur) - F(prev)`.

**5.5.2 Lever lens, level 1 (net revenue).**
`revenue = customers * frequency * AOV`, with `frequency = orders / customers`
and `AOV = revenue / orders`. If `customer` is not mapped:
`revenue = orders * AOV` (2 factors) and customer hypotheses become `not_testable`.

**5.5.3 Lever lens, level 2 (inside AOV).**
`AOV = units_per_order * price_per_unit`, with `units = sum of quantity over
revenue-counted rows` (net of returns). Shapley over 2 factors gives
contributions in AOV units. They are converted to revenue units proportionally:
`revenue_contribution(k) = phi_AOV * (phi_k / delta_AOV)` for k in
{units_per_order, price_per_unit}, when `delta_AOV != 0`. This stays exact because
the level-2 contributions sum to `delta_AOV`. If net units <= 0 in either period,
level 2 is `inconclusive`.

**5.5.4 Masked-shift alert.** `gross_to_net = sum(|phi_i|) / |delta_revenue|`
over level-1 contributions. Alert if `gross_to_net >= 3` and at least one level-1
component has a signal in step 4 (if `delta_revenue == 0`, alert whenever a
component has a signal).

**5.5.5 Customer lens (additive, exact).** Requires `customer`. Classify every
customer active (at least one revenue-counted row) in `prev` or `cur`:

- new: first purchase in the whole file falls in `cur`;
- resurrected: active in `cur`, not in `prev`, active at some time before `prev`;
- retained: active in both;
- lapsed: active in `prev`, not in `cur` ("lapsed", never "churned": retail is
  not a subscription, and not buying this month is not leaving forever).

Terms: `new_rev`, `resurrected_rev` (their `cur` revenue),
`expansion = sum over retained of max(0, cur - prev)`,
`contraction = -sum over retained of max(0, prev - cur)`,
`lapsed_rev` (the negative of their `prev` revenue), and `unattributed_delta`
(change in revenue from rows with a blank customer).

**Every term is stored signed and the identity is the plain sum** (Thach, 3C):

    delta_revenue = new_rev + resurrected_rev + expansion + contraction
                    + lapsed_rev + unattributed_delta

This paragraph previously defined `contraction` and `lapsed_rev` as positive
magnitudes subtracted from the total. That contradicted CONTRACTS section 7's
example (`"contraction": -88000.0, "lapsed": -219000.0`, which simply add up)
and the file stage 3 writes, so an implementer following the prose would have
negated the two terms twice. Signed terms also put the whole of
`diagnosis.json` under one rule - components sum to the change - the same rule
the Shapley contributions and the PVM effects already follow.

A consequence for step 8: the narration validator must compare **magnitudes**,
so that "lost 219,000" in the AI's sentence matches `-219000.0` in the evidence
it was given (section 5.9).

The same bridge is also computed for the previous transition (month before
`prev` -> `prev`) when history allows, so C1 to C3 can compare flows between
transitions. Left-censoring: if `cur` falls within the first 3 months of the
file, "new" is unreliable and C1/C3 return `inconclusive`.

**5.5.6 Returns lens (additive).** `gross` = revenue of positive-quantity
revenue-counted rows, `returns` = absolute revenue of negative-quantity rows.
`delta_net = delta_gross - delta_returns`.

**5.5.7 Product lens: price-volume-mix on gross sales (exact).** Partition
products (identity per 2C's rules) into: L (positive gross units in both periods),
N (new: `cur` only), X (discontinued: `prev` only).
`delta_gross = delta_gross_L + gross_N(cur) - gross_X(prev)`.
For L, write `gross_L = Q * sum_i(s_i * p_i)` where `Q` = total units in L,
`s_i` = unit share of product i, `p_i` = its average gross price. Shapley with
three players (volume Q, mix vector s, price vector p) yields exact volume, mix
and price effects.

### 5.6 Step 6: Localization

Dimensions are fixed in advance: category (if mapped), product, and customer type
(new / resurrected / retained / lapsed from 5.5.5). RFM segment localization is
excluded because per-customer segments live in Stage 2; segment migration uses
the aggregate counts already in `metrics.json` (hypothesis C4).

Per member: `rev_prev, rev_cur, delta, share_of_change = delta / delta_revenue`.
Members smaller than 2% of `prev` revenue and with fewer than 30 orders in both
periods are grouped as "Other". At most 5 named members per dimension, ranked by
`|delta|`. New and discontinued members are listed separately.

**Mix vs rate for the moved average.** For whichever of AOV or price per unit
moved more in relative terms, split its change across categories into a mix
effect (category shares changed) and a rate effect (within-category values
changed), using 2-player Shapley on `sum_c(share_c * value_c)`. Exact.

**Breadth.**
- `declining_base_share` = share of `prev` revenue held by members whose delta
  has the same sign as the total change.
- `top_member_share` = `|delta|` of the largest member divided by
  `sum(|delta_m|)`.
- Classification: `broad` if `declining_base_share >= 0.70`; `concentrated` if
  `top_member_share >= 0.50`; otherwise `mixed`.

Broad changes point towards calendar, seasonality or a general price move;
concentrated changes point towards a specific product or category.

### 5.7 Step 7: Hypothesis evaluation

**Explained share.** `share = contribution / D`, signed. `D` is the absolute
total of the hypothesis's own lens: `|delta_net|` for the lever, customer and
returns lenses, `|delta_gross|` for the product lens, `|delta_net|` for data and
time hypotheses. When the masked-shift alert is on, `D` becomes the sum of the
absolute contributions of that lens instead. A hypothesis can only be
`supported` if its contribution has the same sign as the change it is meant to
explain.

**Verdicts.**

| Verdict | Rule |
|---|---|
| supported | same sign and share >= 0.20 |
| partial | same sign and 0.05 <= share < 0.20 |
| ruled_out | opposite sign, or share < 0.05, with sufficient data |
| inconclusive | data insufficient (history, left-censoring, too few products) |
| not_testable | no data exists for this cause |

Directional hypotheses (no revenue share) use their own rule, stated per
hypothesis in section 7.

**Lenses must not be summed together.** Each lens reconciles to its own total:
the lever lens and the customer lens to `delta_net`, the product lens to
`delta_gross`, the returns lens to `delta_net`. Calendar and seasonality are
context adjustments, not additive with the lenses. The report shows each lens as
its own breakdown and never adds shares across lenses.

### 5.8 Headline selection (code, not AI)

Evaluated in this order; the first match wins:

1. Trust gate `blocked`: headline states the data problem.
2. D1 supported with share >= 0.50: "most of the change is consistent with
   missing days of data", with the estimated gap.
3. T3 supported (every series within limits) and no masked-shift alert:
   "within normal variation this period".
4. Masked-shift alert: "total looks stable but its components shifted strongly",
   naming the two largest opposing contributions.
5. Calendar or seasonality explains at least 50% of the change: headline states
   that most of the change is calendar or seasonal.
6. Otherwise: the `supported` hypothesis with the largest absolute share across
   all lenses, with the lens named.
7. Nothing supported: "no single tested cause explains most of the change",
   followed by the `partial` hypotheses.

Trust `caution` never changes the headline but is always shown next to it.

### 5.9 Step 8: AI narration

- Input: the complete deterministic output of steps 1 to 7 as JSON. Never raw rows.
- The AI writes: a plain-language summary, an explanation of the headline, a short
  paragraph per supported or partial hypothesis, and one sentence naming what
  could not be tested.
- The AI may not choose, add, remove or re-rank hypotheses, and may not upgrade a
  verdict (an `inconclusive` item cannot be described as a cause).
- Validator (code): every number in the AI text must match a number in the
  evidence (tolerance 0.5% relative, or exact for counts); every hypothesis id
  referenced must exist; the not-testable sentence must be present. Failure uses
  the run's single shared retry, then degraded mode.
- Degraded mode (AI unavailable): `ai_findings = null`, the deterministic headline
  and hypothesis table are still shown. Stage 3 never fails because of the AI.
- Model: `MODEL_REASONING` (ADR-0003).

---

## 6. `diagnosis.json` shape (replaces CONTRACTS section 7)

No `diagnosis.json` has ever been written, so the contract is amended in place at
`schema_version "1.0"` (same precedent as the 0B and 1C amendments).
`contracts/diagnosis.py` is rewritten accordingly. Field-level types are fixed in
the SPECS UPDATE session; the skeleton is:

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-10-01T10:00:00Z",
  "run_id": "uuid",
  "frame": {"current": "2011-11", "previous": "2011-10",
            "year_ago_current": "2010-11", "year_ago_previous": "2010-10",
            "history_months": 23},
  "trust": {"verdict": "trusted | caution | blocked",
            "checks": [{"id": "D1", "status": "ok | caution | blocked | inconclusive",
                        "evidence": {}, "message": "..."}],
            "limitations": ["rows dropped in stage 1 cannot be assigned to a period"]},
  "calendar": {"method": "weekday_weights | day_count", "calendar_effect": 0.0,
               "calendar_adjusted_change": 0.0, "evidence": {}},
  "signals": [{"series": "revenue", "mode": "level | yoy", "value_cur": 0.0,
               "center": 0.0, "lower": 0.0, "upper": 0.0,
               "signal": "above | below | within | insufficient_history",
               "rule": 1}],
  "tree": {
    "method": "shapley",
    "lever": {"level1": {"formula": "customers*frequency*aov",
                         "factors": [{"name": "customers", "value_prev": 0.0,
                                      "value_cur": 0.0, "contribution": 0.0}]},
              "level2": {"formula": "units_per_order*price_per_unit", "factors": []},
              "gross_to_net": 0.0, "masked_shift_alert": false},
    "customers": {"new": 0.0, "resurrected": 0.0, "expansion": 0.0,
                  "contraction": 0.0, "lapsed": 0.0, "unattributed": 0.0,
                  "previous_transition": {}},
    "returns": {"gross_prev": 0.0, "gross_cur": 0.0, "returns_prev": 0.0, "returns_cur": 0.0},
    "products": {"volume": 0.0, "mix": 0.0, "price": 0.0,
                 "new_products": 0.0, "discontinued_products": 0.0}
  },
  "localization": {"dimensions": [{"name": "category", "members": [],
                                   "other": {}, "new_members": [], "removed_members": []}],
                   "mix_rate": {"metric": "aov", "mix": 0.0, "rate": 0.0},
                   "breadth": {"declining_base_share": 0.0, "top_member_share": 0.0,
                               "classification": "broad | concentrated | mixed"}},
  "hypotheses": [{"id": "P2", "family": "price_mix", "lens": "product",
                  "statement": "Customers shifted towards cheaper products",
                  "verdict": "supported | partial | ruled_out | inconclusive | not_testable",
                  "contribution": 0.0, "share": 0.0, "evidence": {}, "rule": "..."}],
  "not_testable": [{"id": "X1", "statement": "Marketing or promotion changes"}],
  "headline": {"rule": 6, "hypothesis_id": "P2", "lens": "product"},
  "ai_findings": null
}
```

When the trust gate is `blocked`: `calendar`, `signals`, `tree` and
`localization` are `null`, every hypothesis except the D family is
`inconclusive`, and the headline uses rule 1.

---

## 7. Hypothesis catalog (fixed, evaluated in this order every run)

Shares follow section 5.7. "Standard rule" = the verdict table in 5.7.

| Id | Family / lens | Statement | Contribution or test | Rule | Requires |
|---|---|---|---|---|---|
| D1 | data | Days of data are missing | minus the estimated revenue gap (5.2) | standard; also drives headline rule 2 | none |
| D2 | data | Prices shifted uniformly (possible unit or currency issue) | D2 check | directional: supported when D2 is caution | 20 comparable products |
| D3 | data | Flagged rows are concentrated in the current period | D3 check | directional: supported when D3 is caution | none |
| T1 | time | The calendar explains the change | `calendar_effect` | standard | none (day-count fallback) |
| T2 | time | Seasonality explains the change | `revenue_prev * (LY_cur / LY_prev - 1)` | standard | year-ago pair |
| T3 | time | The change is routine variation | all series `within`, no masked alert | directional: supported / ruled_out | 8 baseline points for revenue |
| C1 | customers | Fewer new customers | `new_rev(t) - new_rev(t-1)` | standard | customer, previous transition, no left-censoring |
| C2 | customers | More customers lapsed | `lapsed(t) - lapsed(t-1)` | standard | customer, previous transition |
| C3 | customers | Fewer customers came back | `resurrected_rev(t) - resurrected_rev(t-1)` | standard | customer, previous transition, no left-censoring |
| C4 | customers | Customers migrated to weaker segments | change in share of (At-risk + Hibernating) minus change in share of (Champions + Loyal), from `metrics.json` | directional: supported if unfavorable by >= 5 points, ruled_out if favorable or < 1 point | customer |
| B1 | lever | Customers buy less often | level-1 frequency contribution | standard | customer |
| B2 | lever | Baskets got smaller | level-2 units-per-order contribution in revenue units | standard | net units > 0 |
| P1 | product | Like-for-like prices changed | PVM price effect | standard | products in L |
| P2 | product | Sales mix shifted towards cheaper (or pricier) products | PVM mix effect | standard | products in L |
| P3 | returns | Returns changed | `-delta_returns` | standard | none |
| R1 | localization | The change is concentrated in one product or category | breadth `concentrated` and top member with the same sign as the total | directional; top member's share reported | none |
| R2 | product | Products were launched or discontinued | `gross_N(cur) - gross_X(prev)` | standard | none |
| R3 | product | A top product may have run out of stock | products with active-day rate >= 50% in `prev` and zero sales in the last >= 7 consecutive days of `cur` while the store had sales on those days; contribution = minus (product's mean daily `prev` revenue x zero days) | verdict wording is always "consistent with a stockout, verify on the shelf", never "caused by" | none |

Not testable with DataClarity's schema (always listed, never evaluated):

| Id | Cause | Why |
|---|---|---|
| X1 | Marketing, promotions, discounts | no campaign data; discount columns are not canonical |
| X2 | Competitor actions | no external data |
| X3 | Weather, macro events | no external data |
| X4 | Store traffic and conversion | no footfall or session data |
| X5 | Margin changes | no cost field |
| X6 | Country or region | no canonical country field (2D decision) |
| X7 | Sales channel or payment method | not canonical fields (Backlog: generic extra dimensions) |

---

## 8. Validation: planted-cause scenario suite

A deterministic generator (fixed seed) builds a realistic synthetic store: 26
complete months, about 400 customers, 6 categories x 10 products with
category-dependent prices, daily orders with retail weekday weights (Saturday
heaviest), small random noise, a small share of returns. Each scenario modifies
only what its cause requires.

| Id | Planted cause | Expected result |
|---|---|---|
| S0 | nothing (noise only) | headline rule 3 (normal variation); zero hypotheses `supported` |
| S1 | `cur` = March, `prev` = February, no business change | T1 supported; headline rule 5 (calendar) |
| S2 | like-for-like prices -20% in one category | P1 supported; that category is the top localized member |
| S3 | demand shifts to the cheapest category (share 50% -> 80%), prices unchanged | P2 supported; P1 ruled_out |
| S4 | 30% of customers active in `prev` do not buy in `cur` | C2 supported and headline |
| S5 | 6 consecutive days of rows removed from `cur` | D1 supported; trust `caution`; headline rule 2 |
| S6 | customers -40%, AOV +40% (net close to flat) | masked-shift alert; headline rule 4 |
| S7 | best-selling product has zero sales in the last 10 days of `cur` | R3 "consistent with a stockout" |
| S8 | 3 products discontinued in `cur` | R2 supported |
| S9 | every December x1.6 in all years; `cur` = January, `prev` = December | T2 supported; headline rule 5 (seasonal) |
| S10 | all prices x100 in `cur` (cents entered as units) | D2 flagged; trust `caution` |
| S11 | no planted cause; the build is truncated to its last 6 complete months | every signal `insufficient_history`; calendar `weekday_weights`; T3 `inconclusive`; headline must NOT be rule 3 (normal variation); no hypothesis `supported` |

S11 is the only scenario that plants nothing and still must not produce rule 3.
S0 plants nothing either, but S0 has 26 months behind it, so "within normal
variation" is a true statement there and the expected headline. On a six-month
file the engine has no baseline to call anything normal by: every series is
`insufficient_history` and T3 is `inconclusive`, so rule 3 would be asserting a
verdict the data cannot support. The two scenarios are therefore a matched
pair - same planted cause, opposite expected headline - and the difference
between them is the whole point: the engine has to know when to stay silent.
Note that the split inside S11 is real and not a bug: step 3 needs 56 calendar
days of history and step 4 needs 8 whole months, so the same file legitimately
gets true weekday weights while every XmR series reports no baseline.

Acceptance criteria (tests fail otherwise):

1. Every scenario produces its expected headline or expected verdict.
2. S0 produces zero `supported` hypotheses.
3. Across the whole suite, at most 1 `supported` hypothesis that is not implied by
   its scenario's planted cause. Each scenario declares its implied set (for
   example, S4 also implies the customers factor of the lever lens).

The suite's results (headline accuracy, decoy count, null false alarms) are
printed by the tests and quoted in the README: this is the evidence that the
engine works.

---

## 9. Constants (`stages/diagnose/thresholds.py`)

Thresholds are documented constants inside the Stage 3 package, not `.env`
settings: stages cannot read backend Settings, and the project's rule of no
defaults in `.env` would otherwise add a mandatory line per threshold. All values
are heuristic defaults, to be revisited against real data.

| Constant | Default | Used in |
|---|---|---|
| SUPPORTED_MIN_SHARE | 0.20 | 5.7 |
| PARTIAL_MIN_SHARE | 0.05 | 5.7 |
| HEADLINE_CONTEXT_MIN_SHARE | 0.50 | 5.8 rules 2 and 5 |
| MASKED_GROSS_TO_NET | 3.0 | 5.5.4 |
| XMR_FACTOR | 2.66 | 5.4 |
| XMR_MIN_BASELINE_POINTS | 8 | 5.4 |
| XMR_RUN_LENGTH | 8 | 5.4 rule 2 |
| YOY_MODE_MIN_MONTHS | 25 | 5.4 |
| HISTORY_MAX_MONTHS | 24 | 5.1 |
| CALENDAR_MIN_WEEKS | 8 | 5.3 |
| D1_CAUTION_DAYS / D1_CAUTION_SHARE | 3 / 0.10 | 5.2 |
| D1_BLOCK_SHARE | 0.50 | 5.2 |
| D2_MIN_PRODUCTS / D2_MIN_ROWS | 20 / 3 | 5.2 |
| D2_CLUSTER_SHARE / D2_CLUSTER_WIDTH | 0.80 / 0.02 | 5.2 |
| D2_NEUTRAL_BAND | 0.90 to 1.10 | 5.2 |
| D3_RATIO / D3_MIN_SHARE | 2.0 / 0.02 | 5.2 |
| MEMBER_MIN_REVENUE_SHARE / MEMBER_MIN_ORDERS | 0.02 / 30 | 5.6 |
| MEMBERS_PER_DIMENSION | 5 | 5.6 |
| BREADTH_BROAD / BREADTH_CONCENTRATED | 0.70 / 0.50 | 5.6 |
| C4_SUPPORT_POINTS / C4_RULE_OUT_POINTS | 5.0 / 1.0 | 7 |
| LEFT_CENSOR_MONTHS | 3 | 5.5.5 |
| R3_MIN_ACTIVE_DAY_RATE / R3_MIN_ZERO_RUN_DAYS | 0.50 / 7 | 7 |
| AI_NUMBER_TOLERANCE | 0.005 | 5.9 |

---

## 10. Impact on existing work

| Area | Impact | Safety check |
|---|---|---|
| Stage 1 | none (dropped-rows-per-month is Backlog) | n/a |
| Stage 2 | import paths only: parsing helpers move to `shared/` | all existing Stage 2 tests pass with no test edited |
| `contracts/diagnosis.py` | rewritten | never written to disk, nothing depends on it |
| Backend | new `POST /api/runs/{id}/diagnose`; possibly a `diagnosed` status with an Alembic migration (decided in session 7) | existing endpoints untouched; migration tested as in 1G |
| Stages 4 and 5 | documentation of their inputs follows the new `diagnosis.json` | no code exists yet |
| Frontend | none; the Insights screen is not built | n/a |
| Figma | Insights frame gains a trust badge, a "normal variation" state, the hypothesis list with verdict labels | design only, not urgent |
| `prompts/root_cause.md` | rewritten for narration-only (5.9) | prompt test updated |

---

## 11. Session plan (7 sessions)

| # | Session | Delivers | Decisions it may raise | Doubt-review |
|---|---|---|---|---|
| 1 | SPECS UPDATE (docs only) | CONTRACTS 7, AI_PIPELINE 7, `root_cause.md`, Phase 3 checklist split into 7 lines, thresholds list, ADR-0004 (Shapley and the fixed catalog) | threshold defaults | no |
| 2 | Foundations and checks | parsing helpers moved to `shared/`; steps 1 to 4 (frame, trust gate, calendar, signals); Stage 2 / Stage 3 consistency test | behaviour below 8 months of history | optional; split into 2a/2b if long |
| 3 | Metric tree | 5.5 in full: Shapley levels 1 and 2 with fallback, masked-shift alert, customer bridge (both transitions), returns lens, PVM | lapse window (1 month default) | yes |
| 4 | Localization | 5.6: members, Other grouping, new/removed members, mix vs rate, breadth | final dimension list | yes |
| 5 | Hypotheses and scenarios | section 7 catalog, verdicts, headline rules, section 8 generator and suite | acceptance thresholds | yes |
| 6 | AI narration | 5.9: prompt, validator, degraded mode, one real API check (a few cents) | tone and length | yes |
| 7 | Assembly and endpoint | full `diagnosis.json`, `/diagnose` endpoint, state machine | `diagnosed` status or not | optional |

Only session 6 spends API credit.

---

## 12. Open decisions to settle in the SPECS UPDATE session

1. Confirm or adjust the threshold defaults in section 9.
2. Lapse window: 1 month (consistent with 2A periods, noisier) or activity in the
   last 3 months (steadier, less comparable with Stage 2).
3. ADR-0004 content and title.
4. When to update the Figma Insights frame (now or before Phase 6).
5. Second demo dataset: the current Kaggle file (synthetic, static prices, 25
   customers) will show P1 always ruled out and C1 mostly inconclusive. Online
   Retail II (thousands of customers, real price variation) is recommended for
   demos, alongside the scenario suite.

---

## 13. Honest limitations (stated in the report, not hidden)

- Observational data: decompositions show contributions and consistency, not
  causation.
- Monthly "lapsed" is not permanent churn in retail.
- Rows dropped by Stage 1 cannot be assigned to a period yet.
- R3 is a signal only; point-of-sale data cannot confirm a stockout. Published
  POS-only detectors catch roughly 63% of stockouts with about 15% false alerts.
- Thresholds are heuristics until calibrated on real data.
- Only the dimensions in the canonical schema can be localized.

---

## 14. References

- Sequoia Capital Data Science, Analyzing Metric Changes Part V (Mix Shift) and
  Part VII (Action Plan): https://articles.sequoiacap.com/metrics-mix-shift,
  https://articles.sequoiacap.com/analyzing-metric-changes-part-vii-action-plan
- Levers Labs, Five Causal Factors of Metric Drift and Root Cause Analysis with
  Metric Trees: https://www.leverslabs.com/article/five-causal-factors-of-metric-drift,
  https://www.leverslabs.com/article/root-cause-analysis-with-metric-trees
- Tribe Capital, A Quantitative Approach to Product Market Fit (growth accounting):
  https://tribecap.co/essays/a-quantitative-approach-to-product-market-fit
- Jonathan Hsu, Diligence at Social Capital Parts 1 and 2 (user and revenue growth
  accounting), Medium
- US Census Bureau, X-13 seasonal adjustment Q&A (trading day effects):
  https://www.census.gov/data/software/x13as/seasonal-adjustment-questions-answers.html
- Statistics Canada, calendar effects in retail sales:
  https://www150.statcan.gc.ca/n1/pub/11-010-x/2010003/article/11141-eng.pdf
- Donald Wheeler interview on XmR charts (Stacey Barr):
  https://www.staceybarr.com/measure-up/interview-donald-wheeler-on-interpreting-signals-from-our-kpis/
- Deming Alliance, Process Behaviour Charts, An Introduction:
  https://demingalliance.org/resources/articles/process-behaviour-charts-an-introduction
- Spotify Confidence glossary, Garden of forking paths:
  https://confidence.spotify.com/glossary/garden-of-forking-paths
- Gelman and Loken, The garden of forking paths:
  https://sites.stat.columbia.edu/gelman/research/unpublished/p_hacking.pdf
- Shapley decompositions and order dependence of sequential decomposition:
  https://arxiv.org/pdf/2303.07773
- Ang, The LMDI approach to decomposition analysis: a practical guide (2005)
- Price-volume-mix tie-out discipline: https://tacticfinancial.com/the-tactical-room/pvm-analysis/
- Tableau, How Explain Data Works:
  https://help.tableau.com/current/pro/desktop/en-us/explain_data_explained.htm
- Hidden Markov model for out-of-stock detection from POS data (MSOM):
  https://dl.acm.org/doi/abs/10.1287/msom.2018.0732
- Considered and deferred (few dimensions in the schema): wise-pizza
  (https://github.com/transferwise/wise-pizza), Adtributor and successors
  (https://arxiv.org/pdf/2205.10004)
