"""The evidence board copies its numbers from results.json and its drift check passes."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("evidence_board", ROOT / "scripts/evidence_board.py")
board = importlib.util.module_from_spec(spec)
spec.loader.exec_module(board)
RESULTS = json.loads((ROOT / "results.json").read_text())


def test_committed_board_json_matches_results():
    assert json.loads((ROOT / "docs/evidence_board.json").read_text()) == board.numbers(RESULTS)


def test_board_numbers_are_copied_not_invented():
    n = board.numbers(RESULTS)
    runs = RESULTS["scenarios"]["runs"]
    assert n["b_chat_p99_s"]["2_incident"] == runs["2_incident"]["chat_latency_s"]["p99"]
    assert n["c_month"]["multiplier"] == RESULTS["month"]["month_bill_multiplier"]
    assert [p["bill_multiplier"] for p in n["a_share_sweep"]] == [p["bill_multiplier"] for p in RESULTS["share_sweep"]]


def test_board_numbers_follow_results_changes():
    changed = copy.deepcopy(RESULTS)
    changed["scenarios"]["runs"]["2_incident"]["chat_latency_s"]["p99"] += 1
    assert board.numbers(changed) != board.numbers(RESULTS)


def test_board_check_script_passes():
    pytest.importorskip("matplotlib")
    out = subprocess.run([sys.executable, "scripts/evidence_board.py", "--check"], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
