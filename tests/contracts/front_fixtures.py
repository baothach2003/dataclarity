"""The frontend's front-section fixtures (the report redesign, step 5): the
three real runs' report.json as stage 5 writes it today - stage 4 re-run, so
the suggested actions are code's - beside each run's bridge (diagnosis.json
tree.lever.bridge, the figures the waterfall draws), plus the Kaggle run with
its currency confirmed as GBP (the ISO code on amounts, never on counts).
test_frontend_fixtures.py proves each file equals this output, so the page's
tests never pass on a report stage 5 would not write.

Regenerate: python -m tests.contracts.front_fixtures
"""

import copy
import json
from pathlib import Path
from typing import Any

from contracts.diagnosis import DiagnosisContract
from contracts.metrics import MetricsContract
from stages.predict.assemble import predict
from tests.stages.report.real_runs import build_real, files

FRONT_FIXTURES = Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages" / "frontFixtures"
CASES = ("kaggle", "demo_classed", "demo_unanswered", "kaggle_gbp")


def front_fixture(case: str) -> dict[str, Any]:
    run = "kaggle" if case == "kaggle_gbp" else case
    data = files(run)
    code = "GBP" if case == "kaggle_gbp" else None  # stage 4 writes a claim's money in the confirmed currency
    forecast = predict(MetricsContract.model_validate(data["metrics.json"]),
                       DiagnosisContract.model_validate(data["diagnosis.json"]),
                       code=code).contract.model_dump(mode="json")
    replaced: dict[str, Any] = {"forecast": forecast}
    if case == "kaggle_gbp":
        cleaning = copy.deepcopy(data["cleaning_report.json"])
        cleaning["currency"] = {"code": "GBP", "source": "user", "evidence": None}
        replaced["cleaning"] = cleaning
    report = build_real(run, **replaced).model_dump(mode="json")
    return {"report": report, "bridge": data["diagnosis.json"]["tree"]["lever"]["bridge"]}


def written(case: str) -> str:
    return json.dumps(front_fixture(case), indent=1, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    FRONT_FIXTURES.mkdir(exist_ok=True)
    for name in CASES:
        (FRONT_FIXTURES / f"{name}.json").write_text(written(name), encoding="utf-8", newline="\n")
        print(name)
