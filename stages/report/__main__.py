"""`python -m stages.report --run <run_id> --source-file <name>`: see stages/report/cli.py (session 5D)."""

import sys

from stages.report.cli import main

if __name__ == "__main__":  # importing the module never exits (5D review #9)
    sys.exit(main())
