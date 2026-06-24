"""Tests for match_latest() — returns candidate with max mtime, tiebroken by filename."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from open_trace import match_latest


def test_returns_none_for_empty_candidates():
    assert match_latest([]) is None


def test_returns_single_candidate():
    c = {"path": Path("/a/trace.zip"), "mtime": 1000.0, "nodeid_hint": "alpha"}
    result = match_latest([c])
    assert result is c


def test_picks_highest_mtime():
    a = {"path": Path("/a/trace.zip"), "mtime": 1000.0, "nodeid_hint": "a"}
    b = {"path": Path("/b/trace.zip"), "mtime": 2000.0, "nodeid_hint": "b"}
    c = {"path": Path("/c/trace.zip"), "mtime": 1500.0, "nodeid_hint": "c"}
    result = match_latest([a, b, c])
    assert result is b


def test_tiebreaker_by_filename_asc_when_same_mtime():
    a = {"path": Path("/aaa-trace.zip"), "mtime": 1000.0, "nodeid_hint": "aaa"}
    b = {"path": Path("/bbb-trace.zip"), "mtime": 1000.0, "nodeid_hint": "bbb"}
    c = {"path": Path("/ccc-trace.zip"), "mtime": 1000.0, "nodeid_hint": "ccc"}
    result = match_latest([c, a, b])
    assert result is a


def test_tiebreaker_is_deterministic_across_input_orders():
    a = {"path": Path("/x-trace.zip"), "mtime": 500.0, "nodeid_hint": "x"}
    b = {"path": Path("/y-trace.zip"), "mtime": 500.0, "nodeid_hint": "y"}
    r1 = match_latest([a, b])
    r2 = match_latest([b, a])
    assert r1 is r2
