"""go-roster end to end: a CSV in, a TD's worklist out.  All names invented."""
import json
import subprocess
import sys

import pytest

from conftest import BIN

TDLIST = "\n".join([
    "Aldergate, Rowan\t90001\tFull\t5.50000\t6/1/2027\tWMGC\tMA\t0.50\t1/1/2026",
    "Aldergate, Rhys\t90002\tFull\t1.20000\t6/1/2027\tWMGC\tMA\t0.50\t1/1/2026",
    "Brightwood, Sasha\t90003\tFull\t4.98811\t6/1/2027\tWMGC\tMA\t0.40\t6/1/2025",
    "Calloway, Imre\t90004\tFull\t1.74000\t6/1/2027\tMGA\tMA\t0.60\t2/2/2026",
    "Dunmore, Petra\t90005\tFull\t-3.39000\t6/1/2027\tMGA\tMA\t0.70\t3/3/2026",
    "Lewis, Victoria\t90006\tFull\t-3.00000\t6/1/2027\tMGA\tCT\t0.70\t4/4/2026",
    "Fairweather, Tomas\t90007\tFull\t\t6/1/2027\tNYGA\tNY\t\t",
]) + "\n"

REGISTRATIONS = """Timestamp,Your name,AGA ID,Rank you want to play at
2026-01-01,Rowan Aldergate,90002,5d
2026-01-01,Sasha Brightwood,90003,5d
2026-01-01,Imre Calloway,90004,3d
2026-01-01,Petra Dunmore,90005,5k
2026-01-01,V Lewis,90006,3k
2026-01-01,Tomas Fairweather,90007,8k
2026-01-01,Nobody Atall,99999,4k
2026-01-01,Unregistered Person,,6k
"""


@pytest.fixture
def setup(tmp_path):
    tdlist = tmp_path / "tdlist.tsv"
    tdlist.write_text(TDLIST)
    regs = tmp_path / "regs.csv"
    regs.write_text(REGISTRATIONS)
    cfg = tmp_path / "tournament.toml"
    cfg.write_text(f'[tdlist]\npath = "{tdlist}"\n')
    return cfg, regs


def run(cfg, regs, *args):
    return subprocess.run([sys.executable, str(BIN / "go-roster"), *args,
                           "--csv", str(regs), "--config", str(cfg)],
                          capture_output=True, text=True)


def test_columns_are_found_by_substring_not_position(setup):
    """Form exports word their headers as questions; that must not need editing."""
    r = run(*setup, "ids")
    assert r.returncode == 0, r.stderr
    assert "8 registrants" in r.stdout


def test_the_wrong_id_is_flagged_and_the_right_one_suggested(setup):
    """Rowan registered with Rhys's id - one digit off, a real member, same surname."""
    r = run(*setup, "ids")
    assert "GIVEN NAME DISAGREES" in r.stdout
    assert "Aldergate, Rhys" in r.stdout
    assert "→ try 90001" in r.stdout, "naming the defect without the fix is half a job"
    assert "1 digit different" in r.stdout


def test_an_id_belonging_to_nobody_is_separated_from_a_wrong_person(setup):
    r = run(*setup, "ids")
    assert "AGA ID MATCHES NO MEMBER" in r.stdout
    assert "Nobody Atall" in r.stdout


def test_a_missing_id_is_listed_not_screamed_about(setup):
    r = run(*setup, "ids")
    assert "No AGA id on the form" in r.stdout
    assert "Unregistered Person" in r.stdout


def test_an_initial_given_name_lands_in_the_half_checked_bucket(setup):
    r = run(*setup, "ids")
    assert "Only half the name could be checked" in r.stdout
    assert "V Lewis" in r.stdout


def test_acks_silence_a_reviewed_weak_match(setup, tmp_path):
    cfg, regs = setup
    acks = tmp_path / "acks.json"
    acks.write_text(json.dumps({"90006": "V Lewis - checked at the table", "_note": "x"}))
    r = run(cfg, regs, "ids", "--acks", str(acks))
    assert "Only half the name could be checked" not in r.stdout
    assert "previously accepted" in r.stdout


def test_ranks_reports_each_verdict(setup):
    r = run(*setup, "ranks")
    assert "auto-deny (1 step)" in r.stdout and "Brightwood" in r.stdout
    assert "ADJUDICATE" in r.stdout and "Calloway" in r.stdout
    assert "asking DOWN" in r.stdout and "Dunmore" in r.stdout
    assert "no AGA rating on file" in r.stdout and "Fairweather" in r.stdout


def test_a_player_at_their_book_rank_is_not_reported(setup):
    """Lewis asks 3k and -3.00 truncates to 3k: nothing for a TD to decide."""
    r = run(*setup, "ranks")
    assert "5 rated registrants" in r.stdout
    assert "Lewis" not in r.stdout, "an at-book rank is not a ruling"


def test_check_runs_both_audits(setup):
    r = run(*setup, "check")
    assert "verified on BOTH" in r.stdout          # ids
    assert "promotion asks" in r.stdout            # ranks


def test_default_subcommand_is_check(setup):
    cfg, regs = setup
    r = subprocess.run([sys.executable, str(BIN / "go-roster"),
                        "--csv", str(regs), "--config", str(cfg)],
                       capture_output=True, text=True)
    assert "verified on BOTH" in r.stdout and "promotion asks" in r.stdout


def test_a_list_without_the_needed_columns_says_which(setup, tmp_path):
    cfg, _ = setup
    bad = tmp_path / "bad.csv"
    bad.write_text("Timestamp,Email\n2026-01-01,a@example.invalid\n")
    r = run(cfg, bad, "ids")
    assert r.returncode != 0
    assert "aga" in (r.stdout + r.stderr) and "rank" in (r.stdout + r.stderr)


def test_sheet_without_a_reader_names_the_way_out(setup):
    cfg, _ = setup
    r = subprocess.run([sys.executable, str(BIN / "go-roster"), "ids",
                        "--sheet", "abc", "--config", str(cfg)],
                       capture_output=True, text=True)
    assert r.returncode != 0
    assert "--csv" in (r.stdout + r.stderr)
