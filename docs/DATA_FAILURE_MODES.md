# Data failure modes - the catalog

Every known way an input file can be wrong, odd or ambiguous, and what
DataClarity does about it (session 2E-u; Thach, 2026-09-28). The rule each
row is held to: **the correct result or an explicit refusal - never a silent
wrong figure.** A row that does not meet it today says so - LIMIT - and its
case pins today's answer, so a fix fails it loudly; the README's "Known
limitations" lists the main ones, `PROJECT_PLAN.md` 8D every one.

**From now on a new finding enters as a row here plus a case in the
generator** (`tests/data_failures/dirty*.py`, the same id) and the
conformance suite (`tests/data_failures/test_conformance*.py`). The generator
is one small clean file - Ann, Bo and Cy each buy a Mug (10.00) and a Tea
(4.00) every day from 2023-01-01 to 2024-02-29, 42.00 a day - and one fixed
edit per mode, standard library and pandas only (a test parses every import
and the dynamic routes it knows). Each case works its figure by hand, or
asserts the refusal's code, reason or note; a case that depends on stage 1
(its reader, classing, suggestions or cast) runs the production flow - the
bytes as raw.csv, stage 1's profile and execute, then stages 2 and 3. Never
xfail (CONSTRAINTS F1, F2). This catalog lists input shapes; the engine's
own limits on good data stay in 8D.

**Ids** are `DF-` (data failure), a group letter and a number - never a
bare `B1` or `D1`, which name the engine's hypotheses (AI_PIPELINE 7.8).

**Handling.** FIX - a plan transform the user approves (stage 1). ASK - a
Review question; what it does unanswered is stated. FLAG - a stage 1 issue,
a note, a trust caution or a null with its reason, shown beside the
figure. REFUSE - an error code, a blocked run, a cause `not_testable` or
`inconclusive`, a figure withheld. LIMIT - accepted in v1, the consequence
stated; **LIMIT (finding)** marks one that is a silent wrong figure or a
misleading refusal, put to Thach (`PROJECT_PLAN.md` 2E-u's findings).

**Covered by** names an existing test (under `tests/`); "-" means none
before 2E-u: the conformance case is its test (listed at the end).

## A. File structure

| Id | Mode | Detection | Handling | Owner | Covered by |
|---|---|---|---|---|---|
| DF-A1 | File over 50 MB | upload size | REFUSE: FILE_TOO_LARGE (413) | backend | backend/test_upload_service.py::test_rejects_one_byte_over_the_limit_and_removes_the_run |
| DF-A2 | Not a .csv | file name | REFUSE: UNSUPPORTED_TYPE (400) | backend | backend/test_upload_service.py::test_rejects_other_extensions_without_creating_a_run |
| DF-A3 | Empty or header only | no data row | REFUSE: EMPTY_FILE (400) | stage 1 | backend/test_api_schema.py::test_a_header_only_file_is_empty_file_and_fails_the_run |
| DF-A4 | Bytes that are no CSV (a spreadsheet renamed) | binary check, sniffing | REFUSE: PARSE_FAILED (400) | backend, stage 1 | backend/test_upload_service.py::test_rejects_binary_content_renamed_to_csv |
| DF-A5 | Not UTF-8 (latin-1, cp1252) | decoding | FLAG: read as latin-1, `encoding_used` and a warning in the cleaning report | stage 1 | stages/ingest/test_profiling_read.py::test_falls_back_to_latin1_when_the_bytes_are_not_utf8 |
| DF-A6 | Semicolons for commas | delimiter sniff | correct: split on the semicolons | stage 1 | stages/ingest/test_profiling_read.py::test_semicolon_file_with_decimal_commas_is_not_split_on_commas |
| DF-A6b | Decimal commas in the numbers ("10,0"), the whole file | - | LIMIT (finding): no step reads them - stage 1's cast is `pd.to_numeric` - so every price is unmeasurable and the run blocks with a wrong reason ("no sales ... the export was cut short") | stage 1 | - |
| DF-A7 | Duplicate rows | profile count | FLAG: `duplicate_rows`. LIMIT (finding): the plan the AI proposes drops them, and a duplicate cannot be told from a genuine repeat - Online Retail II holds 5,206 such rows (2011-11 revenue -0.3%) | stage 1 | stages/ingest/test_issue_recount.py::test_the_duplicate_rows_description_is_rewritten_from_the_profile_count |
| DF-A8 | A column with no value | profile `null_pct` 100 | FLAG: `all_null_column`; the AI's plan drops it (the default) | stage 1 | stages/ingest/test_ai_schema_checks.py::test_all_null_column_is_checked_against_the_profile |
| DF-A9 | A column with one value | stage 1 count | FLAG: `constant_column` | stage 1 | stages/ingest/test_issue_counts.py::test_constant_column_counts_every_cell_holding_the_one_value |
| DF-A10 | Numbers and words in one column | stage 1 count | FLAG: `mixed_types` | stage 1 | stages/ingest/test_issue_counts.py::test_mixed_types_counts_the_minority_kind_from_either_side |
| DF-A11 | Not sales data at all | the schema step's confidence under 0.5 | REFUSE: NOT_INVENTORY; generic cleaning only | stage 1 (AI), backend | backend/test_api_analyze.py::test_not_inventory_run_is_analysis_failed |
| DF-A12 | No price column mapped | stage 2's required fields | REFUSE: ANALYSIS_FAILED, naming the field | stage 2 | stages/analyze/test_assemble.py::test_missing_unit_price_mapping_propagates |
| DF-A13 | A NUL byte inside a cell | upload's binary check (first 8 KB) | REFUSE in the first 8 KB. LIMIT (finding) past it: the reader ends the cell - "1", NUL, "0.0" reads 1, nothing flagged | backend, stage 1 | backend/test_upload_service.py::test_only_the_first_8_kb_are_checked_for_binary_data |
| DF-A14 | A row with more fields than the header | sniffing | REFUSE: PARSE_FAILED | stage 1 | - |
| DF-A15 | UTF-16 | decoding | correct: read, `encoding_used` says so | backend, stage 1 | backend/test_upload_service.py::test_accepts_utf16_text_even_though_it_contains_nul_bytes |
| DF-A16 | A column named like one stage 1 writes | stage 1 | FLAG: renamed, with a warning (2E-t1) | stage 1 | stages/ingest/test_2et1_execute.py::test_the_rename_is_numbered_when_the_suffixed_name_is_taken |

## B. Dates

| Id | Mode | Detection | Handling | Owner | Covered by |
|---|---|---|---|---|---|
| DF-B1 | Cells that read as no date | the shared date reader | REFUSE: the line left out, `undated_lines` with its reason | shared, stage 2 | stages/analyze/test_2eh_dates.py::test_one_undated_line_is_said_in_the_singular |
| DF-B2 | Two formats in one column | stage 1 count | FLAG: `mixed_date_formats`; both read as one calendar | shared | stages/ingest/test_issue_counts.py::test_mixed_date_formats_counts_the_cells_outside_the_common_format |
| DF-B3 | Day-first or month-first, no cell proves which | order evidence on the raw file | ASK: the date question; unanswered the plan does not run (INVALID_PLAN) - either default fabricates dates | stage 1 | stages/ingest/test_2ej_stage1.py (the order) |
| DF-B4 | A monthly file dated the 1st | month grain | correct: compared as months; T1 not testable, D1 not applied | shared, stages 2-3 | stages/analyze/test_2ej_stage2.py::test_a_month_grain_file_compares_its_last_month |
| DF-B5 | A monthly file dated the month's last day | month grain | correct, as DF-B4 | shared, stages 2-3 | stages/analyze/test_2eo_stage2.py::test_a_month_end_file_is_month_grain_and_compares_its_last_month |
| DF-B6 | A dotted time, then a year ("10.05.30 2026"), in an ISO file | order evidence | ASK (the date question, for the whole file). LIMIT: answered day first it reads 10 May 2030 and moves the file's end there (Thach's Q12: refusing it refuses "05.03.26 2045") | shared, stage 1 | shared/test_2eo_dates.py::test_a_four_digit_year_wins_over_a_dotted_time |
| DF-B7 | Two-digit years, no cell proving the order ("05/02/24") | order evidence | ASK, as DF-B3 | stage 1 | - |
| DF-B8 | The file ends mid-month | the period | correct: the last complete month is compared | stage 2 | stages/analyze/test_2e_stage2.py (period) |
| DF-B9 | The file starts mid-month | complete months | correct: that month stays out of the history | stage 3 | - |
| DF-B10 | The file starts inside the previous month | leading days | REFUSE: every comparison null with its reason; stage 3 blocks | shared, stages 2-3 | stages/analyze/test_2e_stage2.py::test_a_partial_previous_month_makes_every_comparison_unavailable |
| DF-B10b | Days lost inside the previous month | D1 (the previous month too, 3E1) | FLAG: stage 2 compares (it cannot tell a gap from quiet days); D1's caution beside the figures (CLAUDE.md 3.3a) | stage 3 | - |
| DF-B10c | The file starts one or two days into the previous month | - | LIMIT: tolerated (8D "From 5A") - compared with no note, no caution | stage 2 | - |
| DF-B11 | A placeholder date ("0000-00-00") | the date reader | REFUSE: no date, as DF-B1 | shared | shared/test_2ej_dates.py::test_placeholder_dates_are_no_date |
| DF-B12 | Excel's month-year cell ("Feb-24") | - | LIMIT: no day, so no date (8D "From 2E-j") - left out and counted | shared | - |
| DF-B13 | A time with a word, no day ("klo 10.30") | - | LIMIT: no date (8D "From 2E-o") | shared | - |
| DF-B14 | Year-month-day with two-digit years ("24/02/10"), the whole file | - | LIMIT (finding): no question is asked and the dates are misread - the calendar lands in 2001-2031 and the headline names a cause (8D "From 2E-j") | shared, stage 1 | - |
| DF-B15 | One line typed in the future (2042) | - | LIMIT (finding): it moves the current month to 2042-01 and the run blocks, saying the export was cut short | stage 2 | - |
| DF-B16 | Excel's serial date ("45332") | - | LIMIT: no date, left out and counted | shared | - |
| DF-B17 | An AM/PM word ("SA", "CH") after the date | - | LIMIT: no date (8D "From 2E-j") | shared | - |

## C. Amounts and quantities

| Id | Mode | Detection | Handling | Owner | Covered by |
|---|---|---|---|---|---|
| DF-C1 | A quantity that is no number ("one") | the line reader | REFUSE: counted nowhere, listed as unmeasurable "no quantity" | shared, stage 2 | stages/analyze/test_2et2_notes_edges.py::test_a_line_with_neither_quantity_nor_price_is_unmeasurable_for_its_quantity |
| DF-C2 | A blank price | the line reader | REFUSE: unmeasurable "no price" | shared, stage 2 | stages/analyze/test_2et2_stage2.py::test_the_unmeasurable_lines_by_scope_and_reason |
| DF-C3 | "inf" or "nan" written as a number | finiteness | REFUSE: unmeasurable (never a sum that cannot add) | shared, stage 2 | - |
| DF-C4 | A price with a currency sign ("$10.00"), one line | the line reader | REFUSE: unmeasurable, listed - no step reads it (the cast is `pd.to_numeric`) | shared, stage 2 | - |
| DF-C4b | A thousands separator ("1,000.00") on one product's prices | - | LIMIT (finding): every line of that product is unmeasurable and revenue silently becomes the rest's - the lines are listed further down, nothing beside the figure | stages 1-2 | - |
| DF-C4c | Currency signs on every price | - | LIMIT (finding): nothing reads; the run blocks, saying the export was cut short | stages 1-3 | - |
| DF-C5 | A decimal comma in a comma file ("10,5", quoted) | the line reader | REFUSE: unmeasurable, listed, as DF-C4 | shared, stage 2 | - |
| DF-C6 | An outlying price | stage 1 count (quartile fence) | FLAG: `outliers_iqr`; the figure stands as the file has it | stage 1 | stages/ingest/test_issue_counts.py::test_outliers_iqr_counts_the_values_outside_the_fence |
| DF-C7 | Every price x100 (cents read as units), three products or more | D2 | FLAG: trust caution, D2 supported | stage 3 | stages/diagnose/test_frame_and_trust.py::test_d2_flags_a_x100_shift_on_a_five_product_shop |
| DF-C7b | The same with one or two products | - | LIMIT: D2 inconclusive ("no uniform to speak of", AI_PIPELINE 7.3) and the headline names like-for-like prices | stage 3 | - |
| DF-C8 | Amounts too large to add (1e308) | the sum | REFUSE: ANALYSIS_FAILED "a sum too large to add" | stage 2 | backend/test_api_analyze.py::test_amounts_too_large_to_add_up_are_analysis_failed_not_a_500 |
| DF-C9 | A refund at a negative price, quantity positive | the line class | FLAG: contra-revenue (`allowance`) with the `unconfirmed_deductions` note | shared, stage 2 | stages/analyze/test_2et2_stage2.py::test_the_unconfirmed_deductions_note |
| DF-C10 | A zero price | the line class | correct: `no_money`, no money moved | shared | stages/analyze/test_2ec2_stage2.py::test_a_zero_amount_write_off_is_not_a_return |

## D. Line types (`docs/LINE_TAXONOMY.md`)

| Id | Mode | Detection | Handling | Owner | Covered by |
|---|---|---|---|---|---|
| DF-D1 | Return lines (quantity and amount negative) | signs | correct: `customer_return`, contra-revenue | shared | shared/test_2ec_purchase_definition.py::test_a_return_line_needs_a_negative_amount |
| DF-D2 | Online Retail II's cancellations ("C" invoices) | signs | correct: returns (`cancellation` is no class: taxonomy 4.4) | shared | - |
| DF-D3 | Postage or delivery lines (POST, DOT), unanswered | stage 1's words | ASK: suggested "charge"; unanswered, a product - FLAG `unconfirmed_suggestions` | stage 1 | stages/ingest/test_2ed2_stage1.py::test_each_class_word_suggests_its_class |
| DF-D3b | The same, answered | the answer | correct: a charge, other revenue, in `non_product` | shared | shared/test_2ed2_lines.py::test_charges_are_no_orders_and_the_discount_is_no_return |
| DF-D4 | Discount lines, answered | the answer | correct: contra-revenue, in `non_product` | shared | shared/test_2ed2_lines.py::test_charges_are_no_orders_and_the_discount_is_no_return |
| DF-D5 | Fees and costs (AMAZON FEE, BANK CHARGES), answered | the answer | correct: outside revenue, reported | shared | shared/test_2ed2_lines.py::test_costs_and_adjustments_leave_revenue |
| DF-D6 | Adjustments (bad debt), answered | the answer | correct: outside revenue, reported | shared | shared/test_2ed2_lines.py::test_costs_and_adjustments_leave_revenue |
| DF-D6b | The same, unanswered | the line class | FLAG: an unconfirmed deduction (as DF-C9), with its note | shared | stages/analyze/test_2et2_stage2.py::test_the_unconfirmed_deductions_note |
| DF-D7 | A pooled item (Online Retail II's "M"), answered | the answer | correct: sales, never ranked as a product | shared | shared/test_2el_lines.py::test_pooled_lines_are_never_ranked_as_a_product |
| DF-D8 | Gift cards, answered | the answer | correct: a liability, outside revenue | shared | shared/test_2et1_gift_card.py::test_a_confirmed_gift_card_is_left_out_of_revenue_as_a_fee_is |
| DF-D9 | Stock received (typed "in") | the type column | FLAG: outside revenue by sign, with the `returns_booked_as_in` note - a return booked as "in" cannot be told from stock (3.3a) | shared, stage 2 | stages/analyze/test_2et2_stage2.py::test_the_returns_booked_as_in_note |
| DF-D10 | A type other than "in" that disagrees with the signs (a "Return" with quantity +1) | the type column | LIMIT: read by its signs (a sale), with the `other_transaction_types` note beside the figures (taxonomy section 0) | shared, stage 2 | stages/analyze/test_2et2_review2.py::test_the_other_transaction_types_are_bounded |
| DF-D11 | Online Retail II's fee or discount shape (quantity -1, price positive), unanswered | signs, stage 1's words | FLAG: a customer return by its signs, with `unconfirmed_suggestions` | stages 1-2 | - |
| DF-D12 | Online Retail II's "M" (Manual), unanswered | - | LIMIT: ranked as a product, no note | stages 1-2 | - |
| DF-D13 | A non-product word stage 1 misses ("Service charge") | - | LIMIT: ranked as a product, no note (8D "From 2E-d2") | stages 1-2 | - |

## E. Identities

| Id | Mode | Detection | Handling | Owner | Covered by |
|---|---|---|---|---|---|
| DF-E1 | An order id spanning days or customers | stage 1's check (2E-e) | FLAG: `order_id_not_one_order`; kept, orders are counted per id, day and customer | stage 1, shared | shared/test_2ee_orders.py::test_one_id_in_ten_spanning_days_is_still_an_order_id |
| DF-E2 | Blank order ids on some lines | the orders basis | REFUSE: counted as lines, with the reason | shared | shared/test_2ee2_confirmations.py::test_blank_ids_still_fall_back_with_their_exact_count_when_confirmed |
| DF-E3 | A receipt naming its customer on its first line only | receipt fill | ASK: unanswered, the receipt's customer fills its lines (2E-f) | shared | shared/test_2ee2_confirmations.py::test_an_unanswered_fill_question_fills |
| DF-E4 | An order id that is a daily batch or Z-report code | Review | ASK: answered, lines are counted | shared | shared/test_2ee2_confirmations.py::test_a_column_the_user_called_a_batch_code_counts_lines |
| DF-E5 | One product spelled several ways (case, spaces, invisible characters) | the shared text reading | correct: one product | shared | shared/test_2eg_products.py::test_an_invisible_character_inside_a_name_does_not_split_a_product |
| DF-E6 | Labels equal once punctuation is ignored ("Mug." / "Mug") | stage 1 count | FLAG: `near_duplicate_labels`; FIX: the user standardizes | stage 1 | stages/ingest/test_issue_counts.py::test_near_duplicate_labels_ignores_punctuation_and_spacing |
| DF-E7 | Two lines on one business key | stage 1 count | FLAG: `duplicate_business_key` | stage 1 | stages/ingest/test_issue_counts.py::test_duplicate_business_key_marks_every_row_of_a_collision |
| DF-E8 | A customer column mapped but blank for a month | sale lines naming no customer (3E2) | REFUSE: the customer causes `not_testable`, with the reason | stage 3 | stages/diagnose/test_3e2_blank_customers.py |
| DF-E9 | A partly blank customer column (Online Retail II: ~23%) | - | correct: customers are the named ones; unnamed revenue unattributed (2E-f). A mostly-blank month: LIMIT (8D "From 3E2") | shared, stages 2-3 | stages/diagnose/test_3e2_blank_customers.py::test_known_limit_a_month_with_one_named_sale_line_is_read_as_that_customer |
| DF-E10 | Numeric dummy customer ids ("-1") rewritten by a transform | - | LIMIT: `clip` / `fix_negative` can rewrite them before stage 2 compares (8D "From 2E-k" F7). No case: it needs a plan transform on the customer column | stage 1 | - |
| DF-E11 | Unnamed sales and named returns in a month (a refunds desk that records the customer) | - | LIMIT: stage 2's frozen definition counts the refunders as the month's active customers, no note (8D "From 3E2") | stage 2 | - |
| DF-E12 | Review-question edge shapes (2E-e2's K1-K7: whitespace ids, blank ids on stock lines, a fill on a one-customer file, ...) | Review | LIMIT: the question's count or wording, not a figure (8D). No case: Review-level | Review | - |

## F. Placeholders

| Id | Mode | Detection | Handling | Owner | Covered by |
|---|---|---|---|---|---|
| DF-F1 | A walk-in placeholder ("Guest", "Walk-in", "0"), answered | stage 1 candidates | correct: no customer (2E-k) | stage 1, shared | shared/test_2ek_customers.py::test_a_confirmed_placeholder_has_no_customer_in_either_stage |
| DF-F1b | The same, unanswered | stage 1 candidates | ASK. LIMIT (finding): unanswered, "Guest" is one customer buying for every walk-in, no note | shared | - |
| DF-F2 | Numbered walk-in labels ("Walk-in 1".."40") | stage 1 candidates | LIMIT: one question each; unanswered, forty customers (8D "From 2E-k") | stage 1 | - |
| DF-F3 | Missing-value words ("N/A", "null", "NA") | stage 1's reader | correct: blank | stage 1 | - |
| DF-F4 | A cell of invisible characters only | the shared text reading | correct: blank | shared | shared/test_2ei_text.py::test_a_cell_of_only_joiners_or_other_format_characters_is_blank |
| DF-F5 | A dash for a walk-in ("-") | stage 1 candidates | ASK, as DF-F1b - and the same LIMIT unanswered | stage 1 | - |
| DF-F6 | Two equal default accounts (two stores' off-list codes at the same share) | stage 1 candidates | LIMIT: they shield each other from the question (8D "From 2E-r"). No case: a candidate-ranking shape | stage 1 | - |

## G. Coverage

| Id | Mode | Detection | Handling | Owner | Covered by |
|---|---|---|---|---|---|
| DF-G1 | Days lost in the current month (a week) | D1 | FLAG: trust caution; headline rule 2 when they explain the change | stage 3 | stages/diagnose/test_frame_and_trust.py (D1) |
| DF-G1b | One or two days lost | - | LIMIT: under D1's caution (`D1_CAUTION_DAYS` 3, set for sparse shops in 3E1) - no caution, and the headline can give the fall to another cause | stage 3 | - |
| DF-G2 | A month with no line at all | - | LIMIT: charted 0 (3B's recorded defect) | stage 3 | stages/diagnose/test_3e2_blank_customers.py::test_known_limit_a_month_with_no_lines_charts_zero_customers |
| DF-G3 | Fewer than three complete months | the history | REFUSE: no forecast, `insufficient_history` | stage 4 | stages/predict/test_4a_forecast.py::test_insufficient_history_means_fewer_than_three_months |
| DF-G4 | Fewer than eight months of history | the baseline | REFUSE: no chart, `too_few_points` | stage 3 | - |
| DF-G5 | Fewer than two years | the history | REFUSE: no season claimed (SPECS 7.5) | stage 4 | stages/predict/test_4ab_two_year_note.py::test_no_season_claimed_no_two_year_note |
| DF-G6 | A compared month of refunds only | D1 | REFUSE: the diagnosis blocked (rule 1) | stage 3 | stages/diagnose/test_2e_review_fixes.py::test_a_previous_month_of_refunds_only_blocks |
| DF-G7 | A file of one day | the period | REFUSE: the month it does not hold withheld (layer 1); stage 3 blocks | stages 3, 5 | stages/report/test_5a_review3.py (the empty current month) |
| DF-G8 | A "last 30 days" export | the period | REFUSE: stage 3 blocks; layer 1 says where the file starts | stages 3, 5 | stages/report/test_5a_review3.py::test_a_file_starting_part_way_through_the_current_month_says_so_beside_its_figures |
| DF-G10 | A history month of refunds only | - | LIMIT: charted negative (8D "From 5A"); a compared one blocks (DF-G6) | stage 3 | - |
| DF-G11 | A part-way export with an unpriced line on the 1st | - | LIMIT: the file then starts on the 1st, so layer 1's part-way note is not shown (8D) | stage 5 | - |
| DF-G12 | An opening stock-in row months before the first sale | - | LIMIT: left-censoring counts months from any row, so a first-purchase cause can be read as tested (8D "From 2E-o"). No case: the bridge's evidence, pinned in 8D's own tests | stage 3 | - |

## Modes with no test before 2E-u

DF-A6B, DF-A14, DF-B7, DF-B9, DF-B10B, DF-B10C, DF-B12, DF-B13, DF-B14, DF-B15, DF-B16, DF-B17, DF-C3, DF-C4, DF-C4B, DF-C4C, DF-C5, DF-C7B, DF-D2, DF-D11, DF-D12, DF-D13, DF-E10, DF-E11, DF-E12, DF-F1B, DF-F2, DF-F3, DF-F5, DF-F6, DF-G1B, DF-G4, DF-G10, DF-G11, DF-G12 - each now has its conformance case, but DF-E10, DF-E12, DF-F6 and DF-G12, which have none for the reason their rows give.
