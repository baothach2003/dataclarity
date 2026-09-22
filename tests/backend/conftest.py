from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.ai_fakes import FakeResponse
from tests.backend.api_support import Api


@pytest.fixture
def make_api(tmp_path: Path) -> Iterator[Callable[..., Api]]:
    """`make_api(reply, reply, ...)`: an app whose fake AI answers in this order."""
    built: list[Api] = []

    def build(*outcomes: FakeResponse | Exception, **settings: Any) -> Api:
        api = Api(tmp_path, *outcomes, **settings)
        built.append(api)
        return api

    yield build
    for api in built:
        api.engine.dispose()
