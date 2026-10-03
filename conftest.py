import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Collect `testpaths` even when pytest is started from a subdirectory.

    pytest honours `testpaths` only when invoked from the rootdir, so a bare
    `pytest` inside `backend/` (CLAUDE.md section 8) would silently collect
    nothing. This root conftest is loaded from any subdirectory because it sits
    in a parent directory. Runs started inside a test directory, or with explicit
    paths, are left untouched.
    """
    if config.args_source is not pytest.Config.ArgsSource.INVOCATION_DIR:
        return
    testpaths = [config.rootpath / path for path in config.getini("testpaths")]
    invocation_dir = config.invocation_params.dir
    if any(invocation_dir.is_relative_to(path) for path in testpaths):
        return
    config.args = [str(path) for path in testpaths]


# Thach, 2026-10-02: the slow suites carry a marker so a quick run can leave
# them out (`pytest -m "not slow_suite"`); plain `pytest` still runs everything,
# and that is what runs before every commit. By path, so no test file changes.
SLOW_SUITES = ("tests/scenarios/", "tests/data_failures/", "tests/stages/diagnose/test_3e2_")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        path = item.path.relative_to(config.rootpath).as_posix()
        if path.startswith(SLOW_SUITES):
            item.add_marker(pytest.mark.slow_suite)
