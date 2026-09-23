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

# PROVISIONAL (3D6b; 3E re-sweeps it against the real S0-S11 suite and may
# change it). Since ADR-0007 the masked-shift alert no longer reads step 4, so
# "the components moved strongly" needs its own bar, a FLOOR:
#
#     floor = this share * max(typical month, |previous month|, |current month|)
#
# On the ORDERS x AOV pair (not level 1's customers x frequency x AOV), one
# contribution of each sign must clear it. The revenue change must stay under
# the same share of the larger COMPARED month, and the reported three-factor
# `gross_to_net` must reach MASKED_GROSS_TO_NET. The typical month is the
# median |revenue| over the history window's trading months (the 3D6
# yardstick).
#
# Why the pair (Thach, 3D6b): customers x frequency = orders by definition,
# so whenever orders hold steady and the customer count moves, those two
# cancel EXACTLY - the three-factor rule read an identity as a masked shift,
# 19-39% of such months with nothing planted. On the pair: 0-2.4%.
#
# Why the max (Thach, after the doubt-review; the first version used the
# typical month alone): the typical month is small against a peak, so months
# at 3x and 10x typical fired on 15-25% of them with nothing planted. The max
# keeps the rate flat UPWARD and never lets the floor drop below 20% of the
# typical month, so a bad last month cannot shrink it.
#
# Why the change is measured against the compared months, not the floor (pair
# review, a fabrication): in a trough the floor is 20% of a typical month far
# larger than the months compared, so a month that fell 200 -> 50 (-75%)
# passed as "flat" and fired. Against 20% of the larger compared month it
# does not. At or above typical scale the two bounds coincide.
#
# A business materiality threshold. Without noise its must-fire side would be
# definitional; with noise the change also crosses the bound, so S6's shape
# (customers -40%, AOV +40%) is caught 100% without noise and 33-57% with it.
# What was measured is the other side - how often ordinary noise, with
# nothing planted, fires the shipped rule, months at 0.3x / 1x / 3x typical,
# 4,000 draws per cell (scratchpad final_sweep.out):
#     3-factor data, independent 20/10/10                 .000 / .021 / .023
#     3-factor data, independent 30/15/15                 .001 / .050 / .062
#     3-factor data, frequency stable 20/3/10             .000 / .020 / .024
#     orders stable, customers swinging (four structures) .000 / .000-.021 / .000-.024
# (orders*aov-only data, 20% / 10%: .024 / .029 at 1x / 3x, yardstick_sweep.out.)
# The live three-factor ratio removed no alert in those 96,000 draws, nor in a
# targeted search of 400,000 extreme shapes (0 of 16,968 firing; lowest ratio
# 3.43), a search that on the first bound found 169 (bind_search.out). Not
# proven; it can only ever REMOVE an alert.
# These are chosen noise models, not a bound. 0.20 is the smallest share
# keeping the realistic rows (20% / 10% noise) under 3% (share_under_C.out
# has 0.15 and 0.25 for the orders*aov rows, measured on the first bound). A false alarm is a TRUE
# statement - both sides did move that much - in hedged wording, so it
# misleads by emphasis rather than fabricating a finding; it still takes the
# headline from rules 5-7, which is the cost.
MASKED_MIN_CONTRIBUTION_SHARE = 0.20

# A customer whose first purchase falls inside the first few months of the file
# only looks new because the file starts there. C1/C3 stay inconclusive then.
LEFT_CENSOR_MONTHS = 3

# Every decomposition must sum to the total it decomposes. This is the tolerance
# the exactness tests use, and it is a *relative* tolerance: the lenses are
# exact in real arithmetic, so the only gap allowed is floating-point residue,
# which scales with the size of the figures. An absolute tolerance would be
# either meaningless on a shop turning over millions or unmeetable on one
# turning over hundreds (docs/adr/0004, docs/AI_PIPELINE.md 7.6).
RECONCILE_REL_TOLERANCE = 1e-9

# --- Signal vs noise, XmR (7.5) -----------------------------------------------

# Wheeler's two constants for 3-sigma limits on a process behaviour chart:
# 3 / d2 with the AVERAGE moving range (d2 = 1.128 for n = 2), and 3 / d4 with
# the MEDIAN moving range (d4 = 0.954). Both are standard XmR practice.
#
# The median form is preferred because one anomalous month contributes two
# large moving ranges, which the average absorbs and the median does not. On
# the case 3B recorded as finding 3a - a near-zero month producing a huge
# year-over-year point - the average-based limits came out about 650 units
# wide and silenced the series completely, against about 17 for the median.
#
# The average form is kept as the FALLBACK, and it is not a formality. The
# median moving range is exactly zero whenever half the consecutive pairs are
# identical, which is ordinary for flat, rounded or small-integer series
# rather than a degenerate corner - and zero-width limits report a 0.2% move
# as a special cause. Session 3D2 shipped that and measured it: a flat shop at
# 500 went from quiet (limits 485.7 .. 524.3) to firing rule 1 on a move of
# one unit. Falling back to the average is bit-for-bit the behaviour those
# series had before, so the robustness is gained where it helps and nothing
# regresses where it does not.
XMR_FACTOR = 2.66
XMR_MEDIAN_FACTOR = 3.145

# Fewer baseline points than this and the limits are too unstable to act on,
# so the series reports insufficient_history instead of a false verdict.
XMR_MIN_BASELINE_POINTS = 8

# Rule 2: this many consecutive points on one side of the centre line.
XMR_RUN_LENGTH = 8

# --- How small a move is worth reporting (7.5, session 3D3) -------------------
#
# The limits get a MINIMUM WIDTH, and the margin goes back to doing one job.
#
# Until 3D3 these were confused: a single "margin" was asked to absorb
# floating-point residue AND to decide what counts as a business-significant
# move, with floors expressed in money and in fractions. That worked in level
# mode and was meaningless in year-over-year mode, where every series carries
# a PERCENTAGE CHANGE - so a floor of 1e-6 was one millionth of a percentage
# point, i.e. no protection at all. A stable business growing 1% fired rule 1
# every month, and so did a business in an unchanging decline (3D2
# doubt-review C1b, R4, R6 - all of which pre-dated 3D2).
#
# Chosen against `tests/stages/diagnose/test_spread_floor_cases.py`, which is
# the table of cases that MUST fire alongside the ones that must stay quiet.
# The first version of these constants (0.02 and 5.0) was tuned only against
# false alarms, using a sweep whose "break" was always a 50% collapse - a
# break so large no floor could hide it, so the sweep was structurally unable
# to see what the floor suppressed. It silenced a 2% drop on a high-volume
# shop and a grower flipping from +2% to -2.5% year over year (3D3
# doubt-review C1 and R5).
#
# Re-derived: every value in `share <= 0.01` paired with a year-over-year
# floor of 1 to 3 points gets all seven cases right; 0.02 with 5.0 gets four
# of them wrong. These sit in the interior of the passing band, so a small
# mis-calibration does not flip a case.

# Level mode, money and counts: a share of the centre, used only when it is
# WIDER than what the estimators measured - which in practice means a series
# with no variation at all, since 1% of a centre is small next to any real
# month-to-month movement.
XMR_MIN_SPREAD_SHARE = 0.01
# Level mode, rate-like series (a fraction of orders): one percentage point,
# since a share of a centre near 0.02 would be far too small to mean anything.
XMR_MIN_SPREAD_RATE = 0.01
# Year-over-year mode, every series: percentage POINTS, the units the series
# actually carries. 5.0 hid a grower flipping from +2% to -2.5%; 0.0 left an
# unchanging decline firing every month.
XMR_MIN_SPREAD_YOY_POINTS = 2.0

# What a point must clear a limit by, now that significance lives above: this
# is floating-point residue only. A month whose sales and returns cancel
# leaves 4.4e-16 rather than 0.0.
# Sized like residue, not like money: 0.001 was the old business-significance
# number, and on a centre of 1,000,000 it made a margin of 1,000 - which then
# gated rule 2 and silenced genuine runs (3D3 doubt-review R2, R3).
XMR_REL_TOLERANCE = 1e-9
XMR_RESIDUE_FLOOR = 1e-6

# The year-over-year lag. Named because YOY_MODE_MIN_MONTHS is derived from it
# and it is used to shift months in frame.py and signals.py; a bare 12 in three
# files would leave the constant claiming to own something it does not.
YOY_LAG_MONTHS = 12

# --- How small a year-ago month stops being a denominator (7.5, session 3D6) ---
#
# A base is refused when it is below this share of the series' TYPICAL
# magnitude: the median of |value| over the TRADING months (non-zero) of the
# history window, the same months the chart judges against. Scale-free,
# because shops differ by orders of magnitude; a median, so one freak month
# cannot move it (the 3D8 defect); the history window, so a shop is judged
# against its recent self; the magnitude, so a series that nets negative in
# most months still has a size; trading months, because a month without rows
# is charted as 0.0 and a stall open four months a year otherwise had a
# typical level of ZERO and no guard at all (3D6 doubt-review).
#
# Why it mattered while year-over-year rows were verdicts (ADR-0006, until
# ADR-0007): a base of 12.50 on a 50,000 shop divided to +399,900% and fired
# an actionable rule 1 on revenue, `aov` and `units_per_order` on a month that
# went 50,000 to 50,000, and the masked-shift alert then wrote headline rule 4
# without its hedge. Since ADR-0007 the row is descriptive; the guard keeps an
# absurd figure off the page.
#
# THIS IS A POLICY, NOT A MEASUREMENT - the same lesson as 3D5's
# LEVEL_BLIND_SHARE. A base at fraction f of typical is excluded iff f < this
# constant, so a sweep of "bases at f" scored against it is scored against its
# own definition. Worse, the exclusion side has no natural edge at all: a
# comparator at HALF its normal level already fires an actionable +100% on an
# ordinary month, so base effects are what year-over-year is, and no share
# can remove them - it only removes the absurd end, where the figure has
# stopped being a growth rate.
#
# What the sweep DOES measure (scratchpad sweep2/sweep3, 3D6 summary) is the
# upper bound, from bases that are small AND real:
#   - a recovery after a slump of exactly half the window, the brief's "real
#     4,000%": its base sits at 4.76% of a median that averages the two
#     halves. It is lost from 0.045 at 5% monthly noise, from 0.04 at 15%,
#     from 0.035 at 20% and from 0.03 at 30% (1 seed in 80); 0.05 lost 26 of
#     80 seeds even at 5%.
#   - a seasonal trough deeper than the share, whose base is small against
#     the annual median. On a 24-month file a three-month trough last year is
#     indistinguishable from a three-month closure last year - the only other
#     occurrence of that calendar month is the current one, the month being
#     judged - so the trough is excluded with the closure.
#   - a result CAP (refuse any change above N%) was rejected on evidence: it
#     drops a real +9,900% jump by construction.
#   - windows centred on the base (+-6 and +-2 months) were rejected on
#     evidence: a nine-month closure last year passes them and fabricates the
#     verdict this guard exists to stop.
#
# Choosing inside the band uses the ASYMMETRY (Thach, 3D6): refusing a
# usable CURRENT comparator only removes a verdict - T3 goes inconclusive,
# the safe direction - while keeping a base that is too small fabricates one
# that can reach the headline. 0.025 and 0.03 cannot be told apart by any
# shape below 30% noise, so the one that refuses more wins. 0.035 is where
# the brief's own must-fire recovery starts to be lost at 20% noise, a
# realistic figure for monthly retail. (80-seed probe: scratchpad
# edge.shipped.out; shapes: sweep2/sweep3.)
#
# WHAT THIS DOES NOT FIX - two doubt-review cycles, then triaged by running
# each case to the headline. Written while year-over-year rows were verdicts;
# since ADR-0007 each describes a CHART behaviour, not a verdict, and the
# Backlog's "Unusualness verdicts" must fix them before verdicts return:
#   - For a BASELINE base the asymmetry does not hold. Refusing a point moves
#     the centre either way: a shop with a real, growing off-season of about
#     500 against a 50,000 season had six ordinary off-season points refused
#     and its ordinary January became an actionable `above` (then). On ordinary
#     months of two-regime shops the guard gave 23 fabrications against 21
#     without it. It stays on baseline bases for one reason only: below 3% a
#     base drags the centre by thousands of points, which is the reproduction.
#   - It removes the cliff below 3% and nothing above it. A baseline base at
#     3.5%, 5%, 10% or 25% of normal still drags the mean centre far enough
#     that an ordinary -0.5% month fires `below`, rule 1.
#   - A shop off-season for more than half the year at a low but non-zero
#     level has a typical month set by the off-season, so an in-season
#     comparator of 12.50 still charts +400,300%, rule 1.
#   - A slump deeper than about 1.5% of normal, lasting half the window,
#     loses its genuine recovery verdict (the safe direction).
YOY_MIN_BASE_SHARE = 0.03

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
