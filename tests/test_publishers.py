"""og-pairings / og-crosstab / og-stale, driven against the synthetic tournament.

The scoring assertions are hand-computed from the fixture's own results, not
copied from a tool run - otherwise they would only prove the code agrees with
itself.
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import BIN, load_tool

import tdconfig


@pytest.fixture
def pairings(config_file):
    mod = load_tool("og-pairings")
    mod.CFG = tdconfig.load(str(config_file))
    return mod


@pytest.fixture
def crosstab(config_file):
    mod = load_tool("og-crosstab")
    mod.CFG = tdconfig.load(str(config_file))
    return mod


# --- pairings ---------------------------------------------------------------

def test_pairings_page_lists_every_board(pairings):
    cfg = pairings.CFG
    players, games, gps, saved = pairings.load(cfg.newest_xml())
    page = pairings.build_page(players, games, gps, saved, 1)
    assert page.count("<tr") >= 4                      # 4 boards in round 1
    assert "Aldergate" in page and "Everard" in page
    assert cfg.event_title in page
    assert cfg.event_subtitle in page


def test_pairings_marks_the_winner_and_only_the_winner(pairings):
    """Round 1 is white-wins on every board; black must never be marked."""
    players, games, gps, saved = pairings.load(pairings.CFG.newest_xml())
    page = pairings.build_page(players, games, gps, saved, 1)
    assert page.count("class='win'") == 4


def test_index_link_row_is_rewritten_not_duplicated(pairings, site):
    index = site / "event" / "index.md"
    pairings.update_index([1, 2, 3])
    once = index.read_text()
    pairings.update_index([1, 2, 3])
    assert index.read_text() == once, "a second run must not append a second row"
    assert once.count(pairings.MARK_BEGIN) == 1
    assert once.index("# Fixture Open 2026") < once.index(pairings.MARK_BEGIN)


def test_index_row_grows_with_the_rounds(pairings, site):
    pairings.update_index([1])
    pairings.update_index([1, 2, 3])
    text = (site / "event" / "index.md").read_text()
    assert text.count("pairings-r") == 3


def test_unpaired_round_is_refused(config_file):
    r = subprocess.run([sys.executable, str(BIN / "og-pairings"),
                        "--config", str(config_file), "-r", "9", "-n"],
                       capture_output=True, text=True)
    assert r.returncode != 0
    assert "not paired" in (r.stdout + r.stderr)


def test_dry_run_writes_nothing(config_file, site):
    before = sorted(p.name for p in (site / "event").iterdir())
    subprocess.run([sys.executable, str(BIN / "og-pairings"),
                    "--config", str(config_file), "-n"], capture_output=True, text=True)
    assert sorted(p.name for p in (site / "event").iterdir()) == before


# --- cross-tab scoring ------------------------------------------------------
#
# The fixture: 8 players, seeded strongest to weakest, MM bar 5D and floor 28K.
# R1  1>5  2>6  3>7  4>8      (top half wins)
# R2  1>2  3>4  5>6  7>8      (higher seed wins)
# R3  3>1  2>4  5>7  6>8      (seed 3 upsets seed 1)
# So after 3 rounds the win counts are:
#   seed1 2, seed2 2, seed3 3, seed4 1, seed5 2, seed6 1, seed7 1, seed8 0
# (seed 7's single win is round 2 against seed 8 - easy to miss by eye, which is
#  the point of writing these out by hand rather than pasting a tool's output.)

def scored(crosstab, rnd):
    """Keyed by surname; the tool's own `name` is "Surname Given"."""
    cfg = crosstab.CFG
    players, games, gps, _ = crosstab.load(cfg.newest_xml())
    return {p.name.split()[0]: p for p in crosstab.score(players, games, gps, rnd)}


def test_win_counts_match_the_fixture(crosstab):
    table = scored(crosstab, 3)
    got = {name: p.nbw for name, p in table.items()}
    assert got == {"Aldergate": 2, "Brightwood": 2, "Calloway": 3, "Dunmore": 1,
                   "Everard": 2, "Fairweather": 1, "Grissom": 1, "Halloran": 0}


def test_every_player_appears_once(crosstab):
    assert len(scored(crosstab, 3)) == 8


def test_mms_moves_by_one_per_win(crosstab):
    """MMS is a starting score plus one per win; the delta over a round is 0 or 1."""
    r2, r3 = scored(crosstab, 2), scored(crosstab, 3)
    for name in r2:
        assert r3[name].mms - r2[name].mms in (0, 1), name


def test_the_upset_puts_the_winner_on_top(crosstab):
    """Seed 3 beats seed 1 in round 3 and is the only player with three wins."""
    table = scored(crosstab, 3)
    assert max(table.values(), key=lambda p: p.nbw).name.split()[0] == "Calloway"


def test_sos_is_the_sum_of_opponent_mms(crosstab):
    """Recompute one player's SOS from the raw games - the definition, not the code."""
    cfg = crosstab.CFG
    players, games, gps, _ = crosstab.load(cfg.newest_xml())
    table = {p.k: p for p in crosstab.score(players, games, gps, 3)}
    me = next(p for p in table.values() if p.name.startswith("Calloway"))
    opponents = []
    for g in games:
        if int(g["roundNumber"]) > 3:
            continue
        if g["whitePlayer"] == me.k:
            opponents.append(g["blackPlayer"])
        elif g["blackPlayer"] == me.k:
            opponents.append(g["whitePlayer"])
    assert len(opponents) == 3
    assert me.sos == sum(table[o].mms for o in opponents)


def test_crosstab_page_carries_the_configured_event_name(crosstab):
    cfg = crosstab.CFG
    players, games, gps, saved = crosstab.load(cfg.newest_xml())
    table = crosstab.score(players, games, gps, 3)
    page = crosstab.build_page(table, gps, saved, 3, games)
    assert "<title>Fixture Open 2026" in page
    assert "A tournament that does not exist" in page
    assert "Halloran" in page


# --- og-stale ---------------------------------------------------------------

def test_stale_counts_results_on_a_pairings_page(pairings):
    """og-stale reads the deployed page with the same marker the page writes."""
    stale = load_tool("og-stale")
    players, games, gps, saved = pairings.load(pairings.CFG.newest_xml())
    fresh = pairings.build_page(players, games, gps, saved, 1)
    assert stale.shown("pairings", fresh) == 4
    behind = pairings.build_page(players, games, gps, saved, 1).replace("class='win'", "", 2)
    assert stale.shown("pairings", behind) == 2
