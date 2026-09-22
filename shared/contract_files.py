"""Writing one contract file so a reader never sees half of it.

Infrastructure, not analysis (CLAUDE.md section 4). Stage 1 has its own
`stages/ingest/contract_files.py`, which writes *several* files as one
all-or-nothing group with rollback (cleaned.csv + plan_final.json +
cleaning_report.json must appear together or not at all). Stages 2-5 each
write exactly one file per run, so they need the core of that - temp file,
fsync, atomic rename - without the multi-file orchestration. 2D flagged the
duplication when stage 2 needed it; this is where it landed once stage 3
needed it too, rather than a third and fourth copy in stages 4 and 5.
"""

import os
import tempfile
from pathlib import Path


def write_atomically(target: Path, data: bytes) -> None:
    """Write `data` to `target` via a temp file in the same directory, flushed
    and fsynced, then renamed into place. A later reader sees the previous file
    or the complete new one, never a partial write, and a crash mid-write
    leaves the previous file intact.

    Bytes, not text, so no newline is translated on Windows.
    """
    handle, temp_name = tempfile.mkstemp(dir=target.parent, prefix=".stage-", suffix=".tmp")
    temp = Path(temp_name)
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(data)
            out.flush()
            # Without this a crash can leave an empty file behind a rename
            # that already reported success.
            os.fsync(out.fileno())
        os.replace(temp, target)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
