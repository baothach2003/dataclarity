"""The hypothesis catalog, defined ONCE, as data (docs/AI_PIPELINE.md 7.8).

`docs/adr/0005-pre-registered-hypothesis-catalog.md` fixes the catalog before
any run. Twice in Phase 3 a rule lived in two places and the copies drifted
into opposite answers (C2's sign in 3C, T3 in 3D5b), so the catalog now has one
home - this module - and `tests/stages/diagnose/test_catalog.py` fails the
build unless the AI_PIPELINE 7.8 table says exactly the same thing, row by
row. The evaluation code in `hypotheses.py` reads its ids, families and lenses
from here and nowhere else.

`test` is the evidence source and test as the reader sees it; `kind` says how
the verdict is reached:
  term         a term of one of the tree's decompositions; share judged by
               SUPPORTED_MIN_SHARE / PARTIAL_MIN_SHARE, and overshoot above
               100% is real - other terms offset it;
  expectation  an estimate or a between-period difference (what the calendar,
               last year's season, a data gap, a stockout or a change in
               customer flows WOULD have done); supported only if it leaves at
               most 1 - SUPPORTED_MIN_SHARE of the change unexplained, so a
               season that predicted ten times the change does not "explain"
               it (Thach, 3E1);
  directional  a test with no share, whose rule is spelled out in `test`.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class HypothesisSpec:
    id: str
    family: str
    lens: str
    kind: Literal["term", "expectation", "directional"]
    statement: str
    test: str
    requires: str
    # (when it pulled revenue down, when it pushed revenue up). For a cause
    # that can move either way, `statement` is direction-neutral - what is
    # TESTED - and the statement a reader sees is rendered by code from the
    # sign of the contribution ("Customers bought less often" / "more
    # often"). ADR-0005 still holds: the catalog is fixed in advance and
    # nothing chooses what to test; only the wording follows the data,
    # deterministically (Thach, 3E1). A one-way statement tested with a
    # sign-blind rule headlined "baskets got smaller" on a month whose
    # baskets grew 2.7x (3E1 doubt-review).
    rendered: tuple[str, str] | None = None
    # The same hypothesis worded on a LINES basis (2E-e): with no order_id the
    # lever's "orders" are sale lines, so B1 measures lines per customer and B2
    # units per line - a correct reading under its own name, not a refusal.
    lines_statement: str | None = None
    lines_rendered: tuple[str, str] | None = None

    def render(self, sign: float | None, orders_basis: str = "order_id") -> str:
        """The statement for a contribution of this sign; the neutral one when
        there is no signed number. On basis "lines" the lines wording, where
        the hypothesis has one."""
        on_lines = orders_basis == "lines" and self.lines_statement is not None
        statement = self.lines_statement if on_lines else self.statement
        rendered = self.lines_rendered if on_lines else self.rendered
        if rendered is None or not sign:
            return statement
        return rendered[0] if sign < 0 else rendered[1]


@dataclass(frozen=True)
class NotTestableSpec:
    id: str
    statement: str
    reason: str


CATALOG: tuple[HypothesisSpec, ...] = (
    HypothesisSpec(
        "D1", "data_quality", "data", "expectation",
        "Days with no sales (missing data or a closure) explain the change",
        "the previous month's estimated revenue gap minus the current month's, each "
        "priced at its own month's pace; `ruled_out` when the D1 check is `ok`",
        "none"),
    HypothesisSpec(
        "D2", "data_quality", "data", "directional",
        "Prices shifted uniformly (possible unit or currency issue)",
        "directional: supported when D2 cautions",
        "comparable products"),
    HypothesisSpec(
        "D3", "data_quality", "data", "directional",
        "Flagged rows concentrated in the current period",
        "directional: supported when D3 cautions",
        "none"),
    HypothesisSpec(
        "T1", "time", "time", "expectation",
        "The calendar explains the change",
        "`calendar_effect`",
        "none (day-count fallback)"),
    HypothesisSpec(
        "T2", "time", "time", "expectation",
        "Seasonality explains the change",
        "`revenue_prev * (LY_cur/LY_prev - 1)`, with `LY_prev` passing the "
        "year-over-year base guard (7.5), `revenue_prev`, `LY_cur` positive, and "
        "neither year-ago month holding a zero-sale day beyond D1's learned pattern",
        "year-ago pair"),
    HypothesisSpec(
        "T3", "time", "time", "directional",
        "The change is routine variation",
        "**always `inconclusive` in v1** (ADR-0007): no step-4 row is a verdict, "
        "so nothing can establish that the change was routine - "
        "`contracts.diagnosis.is_verdict` decides. If the Backlog's \"unusualness "
        "verdicts\" switches verdicts back on: no rule-1 AND no rule-2 verdict on "
        "any series, no masked alert, and `inconclusive` whenever `revenue` has "
        "no verdict. Evidence lists every series without a verdict",
        "baseline points for revenue"),
    HypothesisSpec(
        "C1", "customers", "customers", "expectation",
        "New-customer revenue changed",
        "`new_rev(t) - new_rev(t-1)`",
        "customer, previous transition, no left-censoring",
        rendered=("New customers brought in less revenue",
                  "New customers brought in more revenue")),
    HypothesisSpec(
        "C2", "customers", "customers", "expectation",
        "Revenue lost to lapsed customers changed",
        "`lapsed(t) - lapsed(t-1)`",
        "customer, previous transition",
        rendered=("Lapsed customers took more revenue away",
                  "Lapsed customers took less revenue away")),
    HypothesisSpec(
        "C3", "customers", "customers", "expectation",
        "Returning-customer revenue changed",
        "`resurrected_rev(t) - resurrected_rev(t-1)`",
        "customer, previous transition, no left-censoring",
        rendered=("Returning customers brought in less revenue",
                  "Returning customers brought in more revenue")),
    HypothesisSpec(
        "C4", "customers", "customers", "directional",
        "Customers moved between segments",
        "**always `inconclusive` in v1**: stage 2's segment counts are a snapshot at "
        "the file's end, not at the end of each compared month. When anchored per "
        "month: change in the (At-risk + Hibernating) share of customers minus change "
        "in the (Champions + Loyal) share; supported if it moved WITH revenue (towards "
        "weaker segments in a fall, stronger in a rise) by at least `C4_SUPPORT_POINTS`, "
        "partial from `C4_RULE_OUT_POINTS`; inconclusive unless all six stage-2 "
        "segments are listed",
        "customer",
        rendered=("Customers migrated to weaker segments",
                  "Customers migrated to stronger segments")),
    HypothesisSpec(
        "B1", "lever", "lever", "term",
        "Purchase frequency changed",
        "level-1 frequency contribution",
        "customer; no excess zero day in either month (D1)",
        rendered=("Customers bought less often",
                  "Customers bought more often"),
        lines_statement="Lines per customer changed",
        lines_rendered=("Customers bought fewer lines",
                        "Customers bought more lines")),
    HypothesisSpec(
        "B2", "lever", "lever", "term",
        "Basket size changed",
        "level-2 units-per-order contribution",
        "net units > 0",
        rendered=("Baskets got smaller",
                  "Baskets got bigger"),
        lines_statement="Units per line changed",
        lines_rendered=("Lines carried fewer units",
                        "Lines carried more units")),
    HypothesisSpec(
        "P1", "product_returns", "product", "term",
        "Like-for-like prices changed",
        "PVM price effect",
        "products in L"),
    HypothesisSpec(
        "P2", "product_returns", "product", "term",
        "Sales mix shifted",
        "PVM mix effect",
        "products in L",
        rendered=("Sales mix shifted towards cheaper products",
                  "Sales mix shifted towards pricier products")),
    HypothesisSpec(
        "P3", "product_returns", "returns", "term",
        "Returns changed",
        "`-delta_returns`",
        "none"),
    HypothesisSpec(
        "R1", "localization_lifecycle", "localization", "directional",
        "The change is concentrated in one product or category",
        "directional: breadth `concentrated` and top member moving with the total",
        "none"),
    HypothesisSpec(
        "R2", "localization_lifecycle", "product", "term",
        "Products were launched or discontinued",
        "`gross_N(cur) - gross_X(prev)`",
        "none"),
    HypothesisSpec(
        "R3", "localization_lifecycle", "product", "expectation",
        "A top product may have run out of stock",
        "a product with at least `MEMBER_MIN_REVENUE_SHARE` of `prev` sales and an "
        "active-day rate at least `R3_MIN_ACTIVE_DAY_RATE` in `prev`, which still "
        "sold in `cur` but then went `R3_MIN_ZERO_RUN_DAYS` consecutive trading "
        "days without a sale; contribution = minus (the product's mean `prev` "
        "revenue per trading day x the zero days)",
        "none"),
)

NOT_TESTABLE: tuple[NotTestableSpec, ...] = (
    NotTestableSpec("X1", "Marketing and promotions",
                    "no campaign data; discount columns are not canonical"),
    NotTestableSpec("X2", "Competitor actions", "no competitor data"),
    NotTestableSpec("X3", "Weather and macro events", "no external data"),
    NotTestableSpec("X4", "Traffic and conversion",
                    "no footfall or session data; sales rows record only purchases"),
    NotTestableSpec("X5", "Margin", "no cost column"),
    NotTestableSpec("X6", "Country or region",
                    "no canonical country field (the 2D finding)"),
    NotTestableSpec("X7", "Sales channel or payment method",
                    "no canonical channel or payment field"),
)

BY_ID: dict[str, HypothesisSpec] = {spec.id: spec for spec in CATALOG}
