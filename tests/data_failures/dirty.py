"""The dirty-file generator of docs/DATA_FAILURE_MODES.md (session 2E-u): one
sample per catalog mode, each a fixed edit of one small clean file
(dirty_base.py), keyed by the catalog row's id. Standard library and pandas
only, across every generator module (a test parses their imports): no
engine figure can shape a sample.
"""

from collections.abc import Callable
from types import ModuleType

from tests.data_failures import dirty_amounts_lines, dirty_files_dates, dirty_people_coverage
from tests.data_failures.dirty_base import Sample


def _cases(module: ModuleType) -> dict[str, Callable[[], Sample]]:
    return {"DF-" + name.upper(): builder for name, builder in vars(module).items()
            if len(name) <= 4 and name[:1] in "abcdefg" and name[1:2].isdigit() and callable(builder)}


# DF- ids: a bare B1 or D1 names one of the engine's hypotheses (AI_PIPELINE 7.8).
SAMPLES: dict[str, Callable[[], Sample]] = (
    _cases(dirty_files_dates) | _cases(dirty_amounts_lines) | _cases(dirty_people_coverage))
