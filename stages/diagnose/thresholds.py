"""Every tunable constant in the stage 3 diagnostic engine
(docs/AI_PIPELINE.md section 7.10).

Constants live here, not in `.env`: a stage may not read backend `Settings`
(docs/SPECS.md section 11 SEC-4, enforced by tests/test_architecture.py), and
the project's "no defaults in `.env`" rule would otherwise add a mandatory
environment variable per threshold.

**All of these are heuristics until calibrated against real data.** They are
documented here with their reasoning so a later session can move one on
evidence rather than taste.
"""

# --- Hypothesis verdicts (7.8) ------------------------------------------------

# A cause must explain a fifth of its lens's movement to be called supported,
# and a twentieth to be worth mentioning at all. Below that it is noise.
SUPPORTED_MIN_SHARE = 0.20
PARTIAL_MIN_SHARE = 0.05

# Headline rules 2 and 5 hand the headline to context (missing data, calendar,
# seasonality) only when that context explains most of the change.
HEADLINE_CONTEXT_MIN_SHARE = 0.50

# --- Metric tree (7.6) --------------------------------------------------------

# sum(|contributions|) / |net change|. At 3x the components are moving several
# times harder than the total, i.e. they are cancelling each other out, which
# is the case a "did revenue move?" report misses entirely.
MASKED_GROSS_TO_NET = 3.0

# A customer whose first purchase falls inside the first few months of the file
# only looks new because the file starts there. C1/C3 stay inconclusive then.
LEFT_CENSOR_MONTHS = 3

# --- Signal vs noise, XmR (7.5) -----------------------------------------------

# Wheeler's constant for process behaviour charts: 3-sigma limits estimated
# from the average moving range (3 / d2, d2 = 1.128 for n = 2).
XMR_FACTOR = 2.66

# Fewer baseline points than this and the limits are too unstable to act on,
# so the series reports insufficient_history instead of a false verdict.
XMR_MIN_BASELINE_POINTS = 8

# Rule 2: this many consecutive points on one side of the centre line.
XMR_RUN_LENGTH = 8

# How far a point must clear a limit before it counts as outside it.
# margin = max(XMR_REL_TOLERANCE * |centre|, the series' absolute floor).
#
# The relative term alone is not enough (Thach, 3B): a series centred on 0.0
# gives a margin of 0.0, so `return_rate` - which is 0.0 every month for most
# shops - would report the shop's first ever return as a statistical signal.
# The absolute floor is what protects that case; the relative term is what
# keeps a rounding cent on a flat 100.0 series quiet without masking a real
# collapse to 40.
XMR_REL_TOLERANCE = 0.001
# Rate-like series (a fraction of orders): one percentage point.
XMR_ABS_FLOOR_RATE = 0.01
# Money and count series: only large enough to absorb floating-point residue -
# a month whose sales and returns cancel leaves 4.4e-16, not 0.0.
XMR_ABS_FLOOR_DEFAULT = 1e-6

# The year-over-year lag. Named because YOY_MODE_MIN_MONTHS is derived from it
# and it is used to shift months in frame.py and signals.py; a bare 12 in three
# files would leave the constant claiming to own something it does not.
YOY_LAG_MONTHS = 12

# Year-over-year mode needs enough months to build XMR_MIN_BASELINE_POINTS YoY
# points before the current one, and each YoY point needs the same month a year
# earlier. Index complete months 1..N with current = N: a YoY point at month m
# needs month m-12, so YoY-capable baseline months run 13..N-1, giving N - 13
# points; requiring XMR_MIN_BASELINE_POINTS of them gives
# N >= YOY_LAG_MONTHS + XMR_MIN_BASELINE_POINTS + 1.
#
# Written as the expression, never as the literal 21: raising the baseline
# requirement must raise the months needed to earn YoY mode, and a hardcoded
# number would silently drift apart from it. A flat 25 was rejected in session
# 3A for being arbitrary and for excluding the recommended demo dataset, which
# has exactly 24 complete months.
YOY_MODE_MIN_MONTHS = YOY_LAG_MONTHS + XMR_MIN_BASELINE_POINTS + 1

# --- Frame and calendar (7.2, 7.4) --------------------------------------------

# Two years of history is enough to estimate weekday weights and XmR limits;
# older months describe a different business.
HISTORY_MAX_MONTHS = 24

# Below this, weekday weights rest on too few observations per weekday, and the
# calendar step falls back to method = "day_count".
CALENDAR_MIN_WEEKS = 8

# --- D1, coverage (7.3) -------------------------------------------------------

# Excess zero-days beyond what this store's own weekday pattern predicts.
D1_CAUTION_DAYS = 3
D1_CAUTION_SHARE = 0.10
D1_BLOCK_SHARE = 0.50

# --- D2, uniform price-level shift (7.3) --------------------------------------

# The confident test: enough products, each with enough rows, for a tight
# cluster of price ratios to mean something.
D2_MIN_PRODUCTS = 20
D2_MIN_ROWS = 3
D2_CLUSTER_SHARE = 0.80
D2_CLUSTER_WIDTH = 0.02
D2_NEUTRAL_BAND = (0.90, 1.10)

# Small-catalog rule (Thach, session 3B). Below D2_MIN_PRODUCTS the confident
# test is not reliable - three products repriced together is an ordinary
# business event, not evidence of a data error - but returning inconclusive
# outright leaves a real hole: a cents-as-units entry error (x100) then flows
# into the product lens, and P1 is reported as "like-for-like prices +9,900%",
# supported, possibly as the headline. A step-4 signal does not prevent that.
#
# So one narrow extra rule, never blocking: an order-of-magnitude jump is a
# unit-error signature, not repricing. Shops with fewer than
# D2_SMALL_MIN_PRODUCTS comparable products stay inconclusive: with one or two
# products there is no "uniform" to speak of.
D2_SMALL_MIN_PRODUCTS = 3
D2_SMALL_CLUSTER_SHARE = 0.80
D2_SMALL_RATIO_HIGH = 5.0
D2_SMALL_RATIO_LOW = 0.2

# --- D3, flagged-row concentration (7.3) --------------------------------------

D3_RATIO = 2.0
D3_MIN_SHARE = 0.02

# --- Localization (7.7) -------------------------------------------------------

MEMBER_MIN_REVENUE_SHARE = 0.02
MEMBER_MIN_ORDERS = 30
MEMBERS_PER_DIMENSION = 5
BREADTH_BROAD = 0.70
BREADTH_CONCENTRATED = 0.50

# --- C4, segment migration (7.8) ----------------------------------------------

C4_SUPPORT_POINTS = 5.0
C4_RULE_OUT_POINTS = 1.0

# --- R3, possible stockout (7.8) ----------------------------------------------

R3_MIN_ACTIVE_DAY_RATE = 0.50
R3_MIN_ZERO_RUN_DAYS = 7

# --- AI narration (7.9) -------------------------------------------------------

# Relative tolerance when checking that every number in the AI's text appears
# in the evidence it was given.
AI_NUMBER_TOLERANCE = 0.005
