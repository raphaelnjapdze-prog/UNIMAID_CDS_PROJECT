"""The training scripts must be runnable the way their own docs say to run them.

Both scripts document `python models/training_script_stageN.py ...`. Invoked that way,
Python puts models/ on sys.path but NOT the repo root, so their `from models.… import`
lines raised ModuleNotFoundError before a single image was read. The failure is silent
until someone has collected a dataset and sits down to train, which is the worst possible
moment to discover it — hence a test rather than a note in the README.

`--help` is enough to catch it: module-level imports run before argparse sees anything.

These are skipped when the ML extras are absent, which includes CI — it installs
requirements-dev.txt only, and nothing else under test imports torch.
"""
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("torch", reason="ML extras not installed (requirements-ml.txt)")

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ["models/training_script_stage1.py", "models/training_script_stage2.py"]


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_runs_as_documented(script):
    """`python models/training_script_stageN.py --help`, exactly as the docstring shows."""
    result = subprocess.run(
        [sys.executable, script, "--help"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, (
        f"{script} cannot be run the way its own usage documents:\n{result.stderr}"
    )


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_runs_as_a_module(script):
    """`python -m models.training_script_stageN` must keep working too.

    The sys.path bootstrap that fixes the direct invocation must not break this one — it
    is the form that works by default, and the one CI-style tooling reaches for.
    """
    module = script.replace("/", ".").removesuffix(".py")
    result = subprocess.run(
        [sys.executable, "-m", module, "--help"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, f"python -m {module} failed:\n{result.stderr}"
