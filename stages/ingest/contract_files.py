"""Writing stage 1 contract files (docs/CONTRACTS.md section 1)."""

import os
import tempfile
from pathlib import Path

from pydantic import BaseModel


def write_contract(target: Path, contract: BaseModel) -> None:
    """Write atomically: a temp file in the same directory, then os.replace,
    so a later stage reads the previous file or the complete new one, never
    half of it."""
    text = contract.model_dump_json(indent=2)
    handle, temp_name = tempfile.mkstemp(dir=target.parent, prefix=".contract-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(text)
        os.replace(temp_name, target)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
