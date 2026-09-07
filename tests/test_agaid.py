"""The name/id matching rules - the part with real judgement in it.

Every name below is invented.  The CASES are drawn from real failure shapes seen
on live rosters (a one-digit id slip landing on a real member, a form name that
is one word, a given name written as an initial), the people are not.
"""
import pytest

from conftest import BIN  # noqa: F401  (puts bin/ on sys.path)

import agaid


def rec(name, **kw):
    d = {"name": name, "rating": None, "club": "", "state": "", "expires": "",
         "last_game": "", "sigma": "", "membership": "", "aga_id": ""}
    d.update(kw)
    return d


TD = {
    "90001": rec("Aldergate, Rowan", rating=5.5),
    "90002": rec("Aldergate, Rhys", rating=1.2),      # same surname, different person
    "90003": rec("Brightwood, Sasha", rating=4.98811),
    "90004": rec("Calloway, Imre", rating=1.74),
    "90005": rec("Lewis, Victoria", rating=-3.0),
    "90006": rec("Yu, Harvy(Chengxi)", rating=2.5),
    "90007": rec("Chen, Wei", rating=-1.5),
    "90008": rec("Chen, Lin", rating=-6.0),
    "90009": rec("Solitary", rating=0.0),             # a record with no comma
}


# --- tokens -----------------------------------------------------------------

def test_single_letters_are_not_evidence():
    """An initial matches far too much; dropping it is what makes 'V Lewis' safe."""
    assert agaid.name_tokens("V Lewis") == {"lewis"}
    assert agaid.name_tokens("R. Aldergate Jr") == {"aldergate", "jr"}


def test_punctuation_and_case_do_not_matter():
    assert agaid.name_tokens("Yu, Harvy(Chengxi)") == {"yu", "harvy", "chengxi"}


def test_a_record_without_a_comma_puts_everything_in_the_given_half():
    """Better than guessing which word is the surname."""
    assert agaid.split_tdlist_name("Solitary") == (set(), {"solitary"})


# --- grading ----------------------------------------------------------------

def test_both_halves_agreeing_is_the_only_full_trust():
    grade, name, _ = agaid.grade_aga_id("Rowan Aldergate", "90001", TD)
    assert grade == agaid.FULL and name == "Aldergate, Rowan"


def test_word_order_does_not_matter():
    """Form text is free-form; the surname is not positionally identifiable."""
    assert agaid.grade_aga_id("Aldergate Rowan", "90001", TD)[0] == agaid.FULL
    assert agaid.grade_aga_id("wei chen", "90007", TD)[0] == agaid.FULL


def test_transliteration_variants_still_match():
    assert agaid.grade_aga_id("Harvy Chengxi Yu", "90006", TD)[0] == agaid.FULL


def test_the_dangerous_case_a_wrong_id_that_shares_a_surname():
    """This is the whole reason the tool grades instead of accepting."""
    grade, name, detail = agaid.grade_aga_id("Rowan Aldergate", "90002", TD)
    assert grade == agaid.LAST
    assert name == "Aldergate, Rhys"
    assert "GIVEN NAME" in detail


def test_the_dangerous_case_a_wrong_id_that_shares_a_given_name():
    """'Wei Zhang' typed the id of 'Chen, Wei': the given name agrees, nothing else."""
    grade, name, detail = agaid.grade_aga_id("Wei Zhang", "90007", TD)
    assert grade == agaid.FIRST and name == "Chen, Wei"
    assert "SURNAME" in detail


def test_sharing_only_a_surname_grades_as_surname_only():
    """'Wei Chen' typed the id of 'Chen, Lin' - a shared surname is not identity."""
    assert agaid.grade_aga_id("Wei Chen", "90008", TD)[0] == agaid.LAST


def test_a_completely_different_person_is_flagged_loudest():
    assert agaid.grade_aga_id("Imre Calloway", "90001", TD)[0] == agaid.NONE


def test_one_word_form_name_is_information_not_an_error():
    grade, _, detail = agaid.grade_aga_id("Sasha", "90003", TD)
    assert grade == agaid.ONEWORD
    assert "one usable token" in detail


def test_an_initial_first_name_grades_as_oneword_not_as_a_mismatch():
    """The generic version of "the form said 'V Lewis'": one usable token."""
    grade, name, _ = agaid.grade_aga_id("V Lewis", "90005", TD)
    assert grade == agaid.ONEWORD
    assert name == "Lewis, Victoria"


def test_one_word_that_matches_nothing_is_still_a_mismatch():
    assert agaid.grade_aga_id("Sasha", "90001", TD)[0] == agaid.NONE


def test_missing_and_unknown_ids_are_separate_grades():
    assert agaid.grade_aga_id("Rowan Aldergate", "", TD)[0] == agaid.NO_ID
    assert agaid.grade_aga_id("Rowan Aldergate", "99999", TD)[0] == agaid.NOT_FOUND


def test_every_grade_that_needs_a_look_has_a_headline():
    for grade, title in agaid.NEEDS_A_LOOK:
        assert title and grade in vars(agaid).values()


# --- suggesting the right id ------------------------------------------------

def test_suggestion_needs_both_names_to_agree():
    """A common surname alone must not drag in every namesake."""
    assert agaid.suggest_aga_id("Chen", "3k", TD) == []
    assert [i for i, _, _ in agaid.suggest_aga_id("Wei Chen", "2k", TD)] == ["90007"]


def test_suggestions_rank_by_agreement_with_the_claimed_rank():
    """Two Aldergates; the claimed rank picks the right one."""
    assert agaid.suggest_aga_id("Rowan Aldergate", "5d", TD)[0][0] == "90001"


def test_suggestion_reports_no_candidate_rather_than_a_bad_one():
    assert agaid.suggest_aga_id("Nobody Here", "3d", TD) == []


@pytest.mark.parametrize("a,b,expected", [
    ("18583", "18593", "1 digit different"),
    ("26524", "26254", "2 digits transposed"),
    ("12345", "12345", ""),
    ("1234", "12345", ""),
    ("11111", "22222", "5 digits different"),
])
def test_digit_typo_describes_the_slip(a, b, expected):
    assert agaid.digit_typo(a, b) == expected


# --- ranks ------------------------------------------------------------------

@pytest.mark.parametrize("rating,rank", [
    (5.50000, "5d"), (4.98811, "4d"), (1.74000, "1d"),
    (-3.39000, "3k"), (-4.95000, "4k"),
])
def test_ratings_truncate_toward_zero(rating, rank):
    assert agaid.rating_to_rank(rating) == rank


def test_the_scale_has_no_zero_rung():
    assert agaid.rank_to_stones("1d") - agaid.rank_to_stones("1k") == 1


@pytest.mark.parametrize("text", ["", "dan", "0k", "41k", "2026", "90001"])
def test_junk_in_the_rank_field_is_rejected(text):
    assert agaid.rank_to_stones(text) is None


def test_rank_asks_are_measured_in_steps_not_rating_delta():
    """Both cases a delta threshold gets wrong, in opposite directions."""
    assert agaid.grade_rank_ask("2d", 1.74) == (agaid.AUTO_DENY, 1)   # delta 0.26
    assert agaid.grade_rank_ask("4k", -4.95) == (agaid.AT_BOOK, 0)    # delta 0.95


def test_two_steps_is_the_only_real_decision():
    assert agaid.grade_rank_ask("3d", 1.2)[0] == agaid.ADJUDICATE
    assert agaid.grade_rank_ask("2d", 1.2)[0] == agaid.AUTO_DENY


def test_asking_down_is_always_denied():
    assert agaid.grade_rank_ask("5k", -3.39)[0] == agaid.DENY_DOWN


def test_an_unrated_player_gets_no_verdict():
    assert agaid.grade_rank_ask("3d", None) == (None, None)
