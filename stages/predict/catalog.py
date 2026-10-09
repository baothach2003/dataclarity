"""Stage 4 Predict - the suggested actions' catalog (the report redesign,
step 4 as Thach's option (d); docs/REPORT_REDESIGN.md 4.3). No AI writes a
recommendation in v1: each claim's action and why are picked here by the
claim's kind and the direction its own figure moved ("up" or "down" - a
refund that fell is "down" whatever it did to sales). Every sentence is
code-written and tested (tests/stages/predict/test_4d_catalog.py): no digit,
no word the front section never uses, no "order", "visit" or "basket" (true
on a file with no order id), no movement word against its direction. The
facts and figures stand beside them in the claim's fact line. A why never
re-reads the figure as a behaviour it does not measure (the review: orders
per customer is no "regular customers bought more"; items per line is no
"bought together"). B1, B2 and P4 have no entry: step 4's scoped review
found none that reads true in every case they reach, so they are no claims
(claims.MOVED_OUT, Thach's stop rule)."""

from typing import Literal

Direction = Literal["up", "down"]

# (kind, direction) -> (action, why). R1 reads the same either way; R3 has one
# entry, worded with stage 3's own words (Thach, Q54).
# R1 names stage 3's top member (`hypotheses[].member`, 18.8; Thach Q62) -
# `{member}`, or its row where a file before 18.8 names none; R3 names the
# appendix's own label for its row (Q61) - `{row}`, stage 3's statement as the
# appendix prints it, placed "in Technical details" (Q70). Filled by claims.py.
_R1 = ("Look at {member} and see what changed there.",
       "The change was concentrated in one product, so that is where to look first.")
_R3 = ("Check the shelf and the stock records for the products in {row}.",
       "Their sales stopped in a way consistent with a stockout - verify on the shelf.")
ACTIONS: dict[tuple[str, str], tuple[str, str]] = {
    ("P1", "up"): ("Watch whether customers keep buying at the new prices.",
                   "Prices of products sold in both months went up; how customers respond shows whether the new "
                   "prices hold."),
    ("P1", "down"): ("Check that the price cuts were intended and are bringing in extra buyers.",
                     "Prices of products sold in both months went down; a price cut pays only when it brings extra "
                     "buyers."),
    ("P2", "up"): ("Keep the pricier products customers chose easy to find.",
                   "Customers chose pricier products among those sold in both months; keeping them easy to find may "
                   "keep that going."),
    ("P2", "down"): ("Show a pricier alternative next to the cheaper products customers chose.",
                     "Customers chose cheaper products among those sold in both months; offering a step up may win "
                     "some of them back."),
    ("C1", "up"): ("Welcome new customers and give them a reason to come back.",
                   "Sales from new customers rose this month; a welcome may turn some of them into regular "
                   "customers."),
    ("C1", "down"): ("Look at how new customers find the shop, and make that easier.",
                     "Sales from new customers fell this month; an easier way in may help them find you."),
    ("C2", "up"): ("Contact customers who have not bought for a while, with a reason to come back.",
                   "Sales lost to customers who stopped buying rose this month; a reminder may bring some of them "
                   "back."),
    ("C2", "down"): ("Keep in touch with customers who have not bought for a while.",
                     "Sales lost to customers who stopped buying fell this month; keeping in touch may keep it that "
                     "way."),
    ("C3", "up"): ("Thank customers who came back after a break.",
                   "Sales from customers who came back after a break rose this month; a thank-you may keep them "
                   "coming."),
    ("C3", "down"): ("Contact customers who have not bought for a while.",
                     "Sales from customers who came back after a break fell this month; a reminder may bring some of "
                     "them back."),
    ("P3", "up"): ("Check the most returned products for faults, sizing or how they are described.",
                   "Refunds for returned goods rose this month; a common reason behind them may be one the shop can "
                   "fix."),
    ("P3", "down"): ("Keep an eye on returns to see whether the lower level holds.",
                     "Refunds for returned goods fell this month; watching them shows whether that lasts."),
    ("P5", "up"): ("Check that postage and other charges are clear before customers pay.",
                   "Postage and other charges paid by customers rose this month; clear charges avoid surprises when "
                   "customers pay."),
    ("P5", "down"): ("Check that postage and other charges are still collected where they should be.",
                     "Postage and other charges paid by customers fell this month; a missed charge may mean the shop "
                     "pays it itself."),
    ("R1", "up"): _R1,
    ("R1", "down"): _R1,
    ("R3", "down"): _R3,
}
