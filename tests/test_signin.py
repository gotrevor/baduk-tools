"""The printed check-in sheet.  Layout arithmetic is the part that bites."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import BIN, FIXTURES

import signin


# --- page arithmetic --------------------------------------------------------

@pytest.mark.parametrize("n,per,expected", [
    (80, 27, [27, 27, 26]),      # even, not 27/27/26-by-accident
    (76, 31, [26, 25, 25]),
    (10, 31, [10]),
    (31, 31, [31]),
    (32, 31, [16, 16]),
    (0,  31, []),
])
def test_pages_split_evenly_not_greedily(n, per, expected):
    """Greedy fill (30/30/20) looks like the sheet ran out, and queues everyone
    at page one."""
    assert signin.page_split(n, per) == expected


def test_every_player_lands_on_exactly_one_page():
    for n in range(1, 200):
        assert sum(signin.page_split(n)) == n


def test_the_page_number_block_is_paid_for():
    """Forgetting it overflowed every page onto a blank sheet, doubling the job."""
    rows = [{"aga_id": str(i), "last": f"Name{i:03d}", "first": "X", "rank": "5k",
             "club": "ABC", "note": ""} for i in range(60)]
    page = signin.render_html(rows, "T", "s")
    height = float(re.search(r"height: ([\d.]+)in", page).group(1))
    assert height * max(signin.page_split(60)) <= signin.BODY_INCHES - signin.PAGENO_INCHES


def test_a_short_list_does_not_get_giant_rows():
    rows = [{"aga_id": "1", "last": "Only", "first": "One", "rank": "3d",
             "club": "", "note": ""}]
    page = signin.render_html(rows, "T", "s")
    assert float(re.search(r"height: ([\d.]+)in", page).group(1)) <= signin.ROW_MAX_IN


# --- names ------------------------------------------------------------------

@pytest.mark.parametrize("full,fallback,expected", [
    ("Lewis, Victoria", "", ("Lewis", "Victoria")),
    ("", "Harvy Chengxi Yu", ("Yu", "Harvy Chengxi")),
    ("", "Jake", ("Jake", "")),          # a desk searches on the last-name column
    ("", "  wei   chen ", ("chen", "wei")),
    ("", "", ("", "")),
])
def test_names_split_for_a_desk_not_for_a_database(full, fallback, expected):
    assert signin.split_name(full, fallback) == expected


@pytest.mark.parametrize("raw,expected", [
    ("4D", "4d"), (" 9K ", "9k"), ("01d", "1d"), ("", ""), ("dan", "dan"),
])
def test_ranks_are_canonicalised(raw, expected):
    assert signin.normalize_rank(raw) == expected


# --- building rows ----------------------------------------------------------

def test_registration_rows_sort_by_last_name():
    people = [{"name": "Zoe Aardvark", "aga_id": "", "asked": "3k"},
              {"name": "Al Zylstra", "aga_id": "", "asked": "1d"}]
    rows, _ = signin.rows_from_registrations(people)
    assert [r["last"] for r in rows] == ["Aardvark", "Zylstra"]


def test_withdrawn_registrants_are_left_off():
    people = [{"name": "Still Here", "aga_id": "", "asked": "3k"},
              {"name": "Gone Away", "aga_id": "", "asked": "99k"}]
    rows, dropped = signin.rows_from_registrations(people)
    assert dropped == 1 and len(rows) == 1


def test_the_aga_spelling_wins_when_the_id_resolved():
    people = [{"name": "harvy chengxi yu", "aga_id": "90006", "asked": "2d"}]
    td = {"90006": {"name": "Yu, Harvy(Chengxi)", "club": "WMGC"}}
    rows, _ = signin.rows_from_registrations(people, td)
    assert (rows[0]["last"], rows[0]["club"]) == ("Yu", "WMGC")


# --- mid-event, from the tournament file ------------------------------------

def test_opengotha_rows_honour_the_participating_flag(tmp_path, tournament_xml):
    """A player who left after round 2 must not be printed for round 3."""
    xml = tmp_path / "t.xml"
    text = tournament_xml.read_text().replace(
        'agaId="90008" club="" country="US" egfPin="" ffgLicence="" '
        'ffgLicenceStatus="" firstName="Bo" grade="15K" '
        'name="Halloran" participating="11111111111111111111"',
        'agaId="90008" club="" country="US" egfPin="" ffgLicence="" '
        'ffgLicenceStatus="" firstName="Bo" grade="15K" '
        'name="Halloran" participating="11000000000000000000"')
    assert text != tournament_xml.read_text(), "fixture shape changed; fix this test"
    xml.write_text(text)
    r3, forced, _ = signin.rows_from_opengotha(xml, 3)
    assert "Halloran" not in [x["last"] for x in r3]
    assert "Halloran" in [x["last"] for x in signin.rows_from_opengotha(xml, 2)[0]]
    assert forced == []


def test_forcing_a_player_on_is_reported_not_silent(tmp_path, tournament_xml):
    xml = tmp_path / "t.xml"
    xml.write_text(tournament_xml.read_text().replace(
        'firstName="Bo" grade="15K" name="Halloran" participating="11111111111111111111"',
        'firstName="Bo" grade="15K" name="Halloran" participating="11000000000000000000"'))
    rows, forced, _ = signin.rows_from_opengotha(xml, 3, add=["90008"])
    assert "Halloran" in [x["last"] for x in rows]
    assert forced and "Halloran" in forced[0]


def test_dropping_a_player_removes_them(tmp_path, tournament_xml):
    rows, _, _ = signin.rows_from_opengotha(tournament_xml, 1, drop=["90001"])
    assert "Aldergate" not in [r["last"] for r in rows]


def test_the_stamp_comes_from_the_tournament_file(tournament_xml):
    _, _, stamp = signin.rows_from_opengotha(tournament_xml, 1)
    assert stamp == "2026-01-01 12:00"


# --- the rendered page ------------------------------------------------------

def test_opengothas_no_club_placeholder_is_not_printed_as_a_club():
    """NoCb is not a club code; printing it makes everyone who skipped the field
    look like a member of one."""
    rows = [{"aga_id": "1", "last": "A", "first": "B", "rank": "5k",
             "club": signin.OG_NO_CLUB, "note": ""}]
    page = signin.render_html(rows, "T", "s")
    assert signin.OG_NO_CLUB not in page
    assert signin.OG_NO_CLUB_DISPLAY in page


def test_every_row_gets_an_initial_box():
    rows = [{"aga_id": str(i), "last": f"N{i}", "first": "X", "rank": "5k",
             "club": "ABC", "note": ""} for i in range(5)]
    page = signin.render_html(rows, "T", "s")
    assert page.count('<td class="box">') == 5


def test_the_sheet_is_printable_on_a_mono_laser():
    """Outline and rule only - no filled bars, no reverse type."""
    rows = [{"aga_id": "1", "last": "A", "first": "B", "rank": "5k", "club": "", "note": ""}]
    page = signin.render_html(rows, "T", "s")
    assert "#000" not in re.sub(r"border[^;]*;", "", page), "no black fills"
    assert "color: #fff" not in page and "color:#fff" not in page


def test_player_names_are_escaped():
    rows = [{"aga_id": "1", "last": "O'<script>", "first": "B & C", "rank": "5k",
             "club": "", "note": ""}]
    page = signin.render_html(rows, "T", "s")
    assert "<script>" not in page and "&amp;" in page


def test_cli_writes_html_without_needing_chrome(config_file, tmp_path):
    out = tmp_path / "sheet.pdf"
    r = subprocess.run([sys.executable, str(BIN / "go-roster"), "signin",
                        "--round", "1", "--html", "--out", str(out),
                        "--config", str(config_file)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    page = out.with_suffix(".html").read_text()
    assert "Fixture Open 2026" in page and "Aldergate" in page
    assert "initial the box if you are here" in page
