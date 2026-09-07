"""aga-rank, rank-audit and rating-changes: the AGA rating-list side.

The TDList rows here are invented.  Format is real (9 tab-separated columns,
no header), the people are not.
"""
import csv
import subprocess
import sys

import pytest

from conftest import BIN, load_tool

# name, aga id, membership, rating, expires, chapter, state, sigma, last game
TDLIST = "\n".join([
    "Aldergate, Rowan\t90001\tFull\t5.50000\t6/1/2027\tWMGC\tMA\t0.50\t1/1/2026",
    "Brightwood, Sasha\t90002\tFull\t4.98811\t6/1/2027\tWMGC\tMA\t0.40\t6/1/2025",
    "Calloway, Imre\t90003\tFull\t1.74000\t6/1/2027\tMGA\tMA\t0.60\t2/2/2026",
    "Dunmore, Petra\t90004\tFull\t-3.39000\t6/1/2027\tMGA\tMA\t0.70\t3/3/2026",
    "Everard, Nia\t90005\tFull\t-4.95000\t6/1/2027\tMGA\tCT\t0.80\t1/1/2019",
    "Fairweather, Tomas\t90006\tFull\t\t6/1/2027\tNYGA\tNY\t\t",
]) + "\n"


@pytest.fixture
def tdlist(tmp_path):
    p = tmp_path / "tdlist.tsv"
    p.write_text(TDLIST)
    return p


# --- rank truncation: the hard rule ----------------------------------------

@pytest.mark.parametrize("rating,expected", [
    (5.50000, ("d", 5)),
    (4.98811, ("d", 4)),      # 4.99 is emphatically a 4d, not a 5d
    (1.74000, ("d", 1)),
    (-3.39000, ("k", 3)),
    (-4.95000, ("k", 4)),
])
def test_truncation_never_rounds(rating, expected):
    assert load_tool("rank-audit").truncate_to_rank(rating) == expected


def test_rank_ladder_has_no_zero_rung():
    m = load_tool("rank-audit")
    assert m.ladder(("d", 1)) - m.ladder(("k", 1)) == 1, "1k -> 1d is one step"
    assert m.ladder(("k", 3)) - m.ladder(("k", 4)) == 1


def test_promotion_ask_is_measured_in_steps_not_rating_delta():
    """+1.74 asking 2d is a full rank on a delta of 0.26; -4.95 asking 4k is none."""
    m = load_tool("rank-audit")
    assert m.ladder(m.parse_rank("2d")) - m.ladder(m.truncate_to_rank(1.74)) == 1
    assert m.ladder(m.parse_rank("4k")) - m.ladder(m.truncate_to_rank(-4.95)) == 0


def test_rank_audit_flags_the_two_step_ask_and_the_demotion(tmp_path, tdlist):
    csv_path = tmp_path / "regs.csv"
    csv_path.write_text(
        "Name,AGA ID,Rank\n"
        "Rowan Aldergate,90001,5d\n"      # book rank, no ask
        "Sasha Brightwood,90002,5d\n"     # book 4d -> one step, auto-deny
        "Imre Calloway,90003,3d\n"        # book 1d -> two steps, adjudicate
        "Petra Dunmore,90004,5k\n"        # book 3k -> asking DOWN
        "Tomas Fairweather,90006,8k\n")   # no rating on file
    cfg = tmp_path / "t.toml"
    cfg.write_text(f'[tdlist]\npath = "{tdlist}"\n')
    r = subprocess.run([sys.executable, str(BIN / "rank-audit"),
                        "--csv", str(csv_path), "--config", str(cfg)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "1 promotion asks" not in r.stdout      # there are two
    assert "2 promotion asks" in r.stdout
    assert "ADJUDICATE" in r.stdout and "Calloway" in r.stdout
    assert "auto-deny" in r.stdout and "Brightwood" in r.stdout
    assert "asking DOWN" in r.stdout and "Dunmore" in r.stdout
    assert "no AGA rating on file" in r.stdout and "Fairweather" in r.stdout


def test_rank_audit_without_a_sheets_command_says_so(tmp_path, tdlist):
    cfg = tmp_path / "t.toml"
    cfg.write_text(f'[tdlist]\npath = "{tdlist}"\n')
    r = subprocess.run([sys.executable, str(BIN / "rank-audit"),
                        "--sheet", "abc123", "--config", str(cfg)],
                       capture_output=True, text=True)
    assert r.returncode != 0
    assert "--csv" in (r.stdout + r.stderr), "must name the way out"


# --- aga-rank ---------------------------------------------------------------

def run_rank(tdlist, *args):
    return subprocess.run([sys.executable, str(BIN / "aga-rank.py"), str(tdlist), *args],
                          capture_output=True, text=True)


def test_aga_rank_finds_a_player_by_id(tdlist):
    r = run_rank(tdlist, "90001")
    assert r.returncode == 0, r.stderr
    assert "Aldergate" in r.stdout and "5d" in r.stdout


def test_aga_rank_finds_by_name_substring(tdlist):
    r = run_rank(tdlist, "bright")
    assert "Brightwood" in r.stdout
    assert "4d" in r.stdout, "4.98811 truncates to 4d"


def test_unrated_rows_are_not_players(tdlist):
    """A member with a blank rating must never appear in a ranking."""
    r = run_rank(tdlist, "90006")
    assert "Fairweather" not in r.stdout or "no rating" in r.stdout.lower()


def test_activity_pool_excludes_the_long_dormant(tdlist):
    """Everard last played in 2019; the 5-year pool must be smaller than 'all'."""
    default = run_rank(tdlist, "90001").stdout
    everyone = run_rank(tdlist, "90001", "--pool", "all").stdout
    n = lambda s: int(__import__("re").search(r"(\d+) players", s).group(1))
    assert n(default) < n(everyone)
