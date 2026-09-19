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
