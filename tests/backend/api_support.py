"""Setup shared by the tests of the stage 1 endpoints (1G): an app on SQLite with the
AI replaced by a fake messages API, so no test can reach the real one (F4)."""

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app.models import Base, Run, RunStatus
from app.services import run_state
from shared.ai_client import AIClient
from tests.ai_fakes import FakeMessages, FakeResponse
from tests.stages.ingest.cleaning_fixtures import RAW_CSV
from tests.stages.ingest.plan_answers import action, dataset_action, plan_answer
from tests.stages.ingest.schema_answers import answer, column

# What the AI would answer for RAW_CSV (cleaning_fixtures): the columns are
# sku, name, qty, price, day, and the plan is the one the 1F tests run.
SCHEMA_COLUMNS = [
    column("sku", "sku", semantic_type="identifier"),
    column("name", "product_name"),
    column("qty", "quantity", semantic_type="numeric_discrete"),
    column("price", "unit_price", semantic_type="numeric_continuous"),
    column("day", "transaction_date", semantic_type="datetime"),
]


def schema_reply(domain_confidence: float = 0.93, **overrides: Any) -> FakeResponse:
    return answer(SCHEMA_COLUMNS, domain_confidence=domain_confidence, **overrides)


def plan_reply() -> FakeResponse:
    return plan_answer(
        [
            action("sku", "trim_whitespace"),
            action("name", "trim_whitespace"),
            action("qty", "fix_negative", params={"strategy": "flag"}),
            action("price", "impute_median"),
            action("day", "parse_datetime"),
        ],
        [dataset_action("remove_exact_duplicates")],
    )


def unusable_reply() -> FakeResponse:
    """An answer that is not JSON: rejected, and the one shared retry is spent on it."""
    return FakeResponse("this is not json")


class Api:
    """The app under test plus the handles a test needs to look behind it."""

    def __init__(
        self,
        tmp_path: Path,
        *outcomes: FakeResponse | Exception,
        **settings_overrides: Any,
    ) -> None:
        self.runs_root = tmp_path / "runs"
        self.messages = FakeMessages(*outcomes)
        # A file, not one shared in-memory connection: every request gets its own
        # connection, so the tests of simultaneous requests are real races.
        self.engine: Engine = create_engine(f"sqlite:///{tmp_path / 'api.db'}")
        Base.metadata.create_all(self.engine)
        self.settings = Settings(  # type: ignore[call-arg]  # remaining fields come from env
            _env_file=None, runs_dir=str(self.runs_root), max_upload_mb=1, **settings_overrides
        )
        self.app: FastAPI = create_app(
            self.settings, engine=self.engine, ai_client_factory=lambda: AIClient(self.messages)
        )
        self.client = TestClient(self.app)

    def upload(self, content: bytes = RAW_CSV, filename: str = "sales.csv") -> str:
        response = self.client.post("/api/runs", files={"file": (filename, content, "text/csv")})
        assert response.status_code == 201, response.text
        run_id: str = response.json()["run_id"]
        return run_id

    def post(self, run_id: str, step: str, body: Any = None) -> httpx.Response:
        return self.client.post(f"/api/runs/{run_id}/{step}", json=body)

    def get(self, run_id: str, step: str) -> httpx.Response:
        return self.client.get(f"/api/runs/{run_id}/{step}")

    def status(self, run_id: str) -> RunStatus:
        with Session(self.engine) as session:
            return session.scalars(select(Run.status).where(Run.id == run_id)).one()

    def error_code(self, run_id: str) -> str | None:
        with Session(self.engine) as session:
            return session.scalars(select(Run.error_code).where(Run.id == run_id)).one()

    def set_status(self, run_id: str, status: RunStatus) -> None:
        with Session(self.engine) as session:
            session.execute(update(Run).where(Run.id == run_id).values(status=status))
            session.commit()

    def file(self, run_id: str, name: str) -> Path:
        return self.runs_root / run_id / name

    def files(self, run_id: str) -> set[str]:
        return {path.name for path in (self.runs_root / run_id).iterdir()}

    def read_json(self, run_id: str, name: str) -> Any:
        return json.loads(self.file(run_id, name).read_text(encoding="utf-8"))

    def write_json(self, run_id: str, name: str, value: Any) -> None:
        self.file(run_id, name).write_text(json.dumps(value), encoding="utf-8")

    @property
    def ai_requests(self) -> int:
        return len(self.messages.calls)


# --- helpers of the tests that drive a run through the steps --------------------------

MakeApi = Callable[..., Api]
UNKNOWN_RUN = "22222222-2222-4222-8222-222222222222"
PLAN_FILES = {"cleaned.csv", "plan_final.json", "cleaning_report.json"}
# Every row lacks a price, so a plan that drops rows missing a price leaves none.
NO_PRICE_CSV = b"sku,name,qty,price,day\nA1,Mug,3,,2024-01-05\nB2,Cup,4,,2024-01-06\n"


def codes(body: dict[str, Any]) -> list[str]:
    return [notice["code"] for notice in body["notices"]]


def analyzed_run(api: Api) -> str:
    run_id = api.upload()
    assert api.post(run_id, "analyze-schema").status_code == 200
    return run_id


def planned(api: Api) -> tuple[str, dict[str, Any]]:
    """A run in `planned`, and the plan the AI proposed for it, as the client holds it."""
    run_id = analyzed_run(api)
    response = api.post(run_id, "plan")
    assert response.status_code == 200, response.text
    plan: dict[str, Any] = response.json()["plan"]
    return run_id, plan


def make_api_with_plan(make_api: MakeApi, **settings: Any) -> tuple[Api, str, dict[str, Any]]:
    api = make_api(schema_reply(), plan_reply(), **settings)
    run_id, plan = planned(api)
    return api, run_id, plan


def edited(plan: dict[str, Any], name: str, **changes: Any) -> dict[str, Any]:
    """The plan after the user changed one column's action."""
    result = copy.deepcopy(plan)
    for column in result["column_actions"]:
        if column["source_name"] == name:
            column.update(changes, edited_by_user=True)
    return result


def price_action(plan: dict[str, Any]) -> str:
    return next(c["action"] for c in plan["column_actions"] if c["source_name"] == "price")


def unmapped_body(plan: dict[str, Any]) -> dict[str, Any]:
    """The plan of a file that is not inventory data: nothing maps to a canonical field."""
    body = copy.deepcopy(plan)
    for column in body["column_actions"]:
        column["canonical_field"] = "ignore"
    return body


def on_ai_call(api: "Api", callback: Callable[[], None]) -> None:
    """Run `callback` at the moment the (fake) AI is asked, before it answers."""
    real = api.messages.create

    def create(**kwargs: Any) -> Any:
        callback()
        return real(**kwargs)

    api.messages.create = create  # type: ignore[method-assign]


def failing_writes(monkeypatch: Any, to: RunStatus, times: int) -> list[int]:
    """Make the database refuse the first `times` writes that move a run to `to`
    (`run_state._transition`, used by every status change)."""
    real = run_state._transition
    refused: list[int] = []

    def flaky(session: Any, run_id: str, target: RunStatus, only_from: Any, *,
               error_code: str | None) -> bool:
        if target is to and len(refused) < times:
            refused.append(1)
            raise OperationalError("UPDATE runs", {}, Exception("database is down"))
        return real(session, run_id, target, only_from, error_code=error_code)

    monkeypatch.setattr(run_state, "_transition", flaky)
    return refused
