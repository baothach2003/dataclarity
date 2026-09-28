"""Stage 3 Diagnose - the line taxonomy in its output (Thach, session 2E-t2;
docs/LINE_TAXONOMY.md sections 3 and 4.5): the notes the standing rule puts
beside a figure (CLAUDE.md 3.3a), carried over from metrics.json - stage 3's
`return_rate` signal and the headline's revenue are figures they qualify -
and `suggested_classes`, every product stage 3 names whose key carries a
line-class suggestion nobody confirmed (Thach's Q17).

Which products a diagnosis.json names is the contract's definition
(`contracts.diagnosis.named_products`), and a product's suggestion is its
own key's (`shared/products.product_suggestions`) - stage 2 reads the same.
"""

from contracts.diagnosis import Hypothesis, Localization, named_products
from contracts.lines import FigureNote
from shared.products import product_keys, product_labels, product_suggestions
from stages.diagnose.inputs import RunData


def stage_3_notes(data: RunData) -> list[FigureNote]:
    """metrics.json's notes, as stage 3's output carries them."""
    return list(data.metrics.core.notes)


def named_suggestions(data: RunData, localization: Localization | None,
                      hypotheses: list[Hypothesis]) -> dict[str, str]:
    """Every product this output names, by label (labels are unique), whose
    own key carries an unconfirmed suggestion, with its class."""
    named = named_products(localization, hypotheses)
    keys = product_keys(data.df, data.parsed)
    labels = product_labels(data.df, data.parsed, keys)
    by_label = {labels[key]: line_class for key, line_class in product_suggestions(data.df, data.parsed, keys).items()}
    return {label: by_label[label] for label in sorted(by_label) if label in named}
