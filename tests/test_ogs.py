"""OGS lookups.  No test here touches the network: the session is a stub."""
import json
import math

import pytest

from conftest import BIN

import ogs


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeSession:
    """Mimics OGS: ?username= is case sensitive; __istartswith is a prefix search."""

    def __init__(self, accounts, fail=False):
        self.accounts = accounts          # username -> rating record
        self.calls = []
        self.fail = fail

    def get(self, url, params=None, timeout=None):
        if self.fail:
            raise ConnectionError("no route to host")
        self.calls.append(params)
        if "username" in params:
            name = params["username"]
            hits = [a for a in self.accounts if a == name]
        else:
            pre = params["username__istartswith"].lower()
            hits = [a for a in self.accounts if a.lower().startswith(pre)]
        return FakeResponse({"count": len(hits),
                             "results": [self.accounts[h] for h in hits]})


def account(username, rating, ranking=None, deviation=60.0, ogs_id=1):
    return {"id": ogs_id, "username": username, "ranking": ranking,
            "ratings": {"overall": {"rating": rating, "deviation": deviation}}}


# --- the rank scale ---------------------------------------------------------

def test_the_fitted_constants_round_trip():
    for ranking in (5, 20, 29, 30, 38):
        rating = ogs.C * math.exp(ogs.A * ranking)
        assert ogs.ranking_from_rating(rating) == pytest.approx(ranking, abs=1e-9)


def test_the_folklore_constants_are_not_what_we_use():
    """850 / 0.032 puts a 24k player at 38k; keeping the real numbers matters."""
    assert (ogs.C, round(ogs.A, 8)) == (525.0, 0.04319654)


@pytest.mark.parametrize("ranking,expected", [(30, "1.0d"), (29, "1.0k"), (38, "9.0d")])
def test_ranking_to_rank_string(ranking, expected):
    assert ogs.rank_str(ranking) == expected


def test_rank_stones_shares_the_aga_ladder():
    """1k -> 1d is one step on both scales, so the two can be subtracted."""
    assert ogs.rank_stones(30) - ogs.rank_stones(29) == 1


def test_a_nonsense_rating_yields_no_ranking():
    assert ogs.ranking_from_rating(0) is None
    assert ogs.ranking_from_rating(-5) is None
    assert ogs.rank_str(None) == "" and ogs.rank_stones(None) is None


# --- lookup -----------------------------------------------------------------

def test_exact_handle_resolves(tmp_path):
    s = FakeSession({"Aldergate": account("Aldergate", 2000, ranking=32)})
    got = ogs.lookup(s, "Aldergate")
    assert got["username"] == "Aldergate" and got["ranking"] == 32


def test_case_insensitive_exact_hit_is_accepted(tmp_path):
    """OGS's ?username= is case sensitive, so this fallback is load-bearing."""
    s = FakeSession({"Aldergate": account("Aldergate", 2000, ranking=32)})
    assert ogs.lookup(s, "aldergate")["username"] == "Aldergate"
    assert "username__istartswith" in s.calls[-1]


def test_a_prefix_is_never_accepted_as_a_match():
    """'kelu' vs 'Kelu' is a different person; a near miss must return nothing."""
    s = FakeSession({"Aldergates": account("Aldergates", 700, ranking=12)})
    assert ogs.lookup(s, "Aldergate") is None


def test_an_ambiguous_prefix_is_refused():
    s = FakeSession({"Chen1": account("Chen1", 1500), "Chen2": account("Chen2", 1600)})
    assert ogs.lookup(s, "Chen") is None


def test_ogs_own_ranking_is_preferred_over_the_formula():
    """OGS applies a 25k display floor; deriving one ignores it."""
    s = FakeSession({"Floor": account("Floor", 400, ranking=5.0)})
    assert ogs.lookup(s, "Floor")["ranking"] == 5.0


def test_ranking_is_derived_when_ogs_omits_it():
    s = FakeSession({"NoRank": account("NoRank", ogs.C * math.exp(ogs.A * 30))})
    assert ogs.lookup(s, "NoRank")["ranking"] == pytest.approx(30, abs=1e-9)


def test_an_unrated_account_is_not_a_result():
    s = FakeSession({"New": account("New", 0)})
    assert ogs.lookup(s, "New") is None


def test_a_wide_deviation_is_flagged_provisional():
    s = FakeSession({"Fresh": account("Fresh", 1500, ranking=25,
                                      deviation=ogs.PROVISIONAL_DEVIATION + 1)})
    assert ogs.lookup(s, "Fresh")["provisional"] is True


# --- caching and failure ----------------------------------------------------

def test_results_are_cached_and_reused(tmp_path):
    cache = tmp_path / "ogs.json"
    s = FakeSession({"A": account("A", 1500, ranking=25)})
    ogs.fetch(["A"], cache, session=s)
    calls = len(s.calls)
    found, _ = ogs.fetch(["A"], cache, session=s)
    assert len(s.calls) == calls, "second run must not hit the network"
    assert found["A"]["username"] == "A"


def test_refresh_bypasses_the_cache(tmp_path):
    cache = tmp_path / "ogs.json"
    s = FakeSession({"A": account("A", 1500, ranking=25)})
    ogs.fetch(["A"], cache, session=s)
    calls = len(s.calls)
    ogs.fetch(["A"], cache, refresh=True, session=s)
    assert len(s.calls) > calls


def test_a_miss_is_cached_too(tmp_path):
    cache = tmp_path / "ogs.json"
    s = FakeSession({})
    _, misses = ogs.fetch(["Ghost"], cache, session=s)
    assert misses == ["Ghost"]
    assert json.loads(cache.read_text())["ghost"]["found"] is False


def test_a_network_failure_keeps_the_last_good_value(tmp_path):
    """A stale rating is information; a blank column is not."""
    cache = tmp_path / "ogs.json"
    ogs.fetch(["A"], cache, session=FakeSession({"A": account("A", 1500, ranking=25)}))
    found, _ = ogs.fetch(["A"], cache, refresh=True,
                         session=FakeSession({}, fail=True), log=lambda *a: None)
    assert found["A"]["ranking"] == 25


def test_a_failure_with_no_previous_value_is_left_blank(tmp_path):
    found, misses = ogs.fetch(["A"], tmp_path / "ogs.json", refresh=True,
                              session=FakeSession({}, fail=True), log=lambda *a: None)
    assert found == {} and misses == []
