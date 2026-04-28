"""Run the evaluation harness from the project root (CI gate). Pass --update-baseline to re-baseline."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from evals.runner import run_evals_cli

if __name__ == "__main__":
    sys.exit(asyncio.run(run_evals_cli(sys.argv[1:])))
