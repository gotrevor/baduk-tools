"""Matching a registration form against the AGA rating list.

This is the part of running a tournament that a computer is actually bad at.  A
registration form gives you free text -- "Jake", "wei chen", "Harvy Chengxi Yu",
a first name that is one initial -- plus an AGA id typed from memory.  The id is
the key that goes into the results file you send to ratings@usgo.org, so a wrong
one attaches somebody's games to a stranger, or to nobody.

The rules here were worked out over several real tournaments.  Two things they
are built around:

**A wrong id usually still finds a real person.**  Go rosters are full of shared
name tokens, so a single mistyped digit lands on someone who shares one and every
other check passes.  Measured on one 2026 roster, both "Micah Feldman" -> the id
of a different Micah and "wei chen" -> the id of a different Chen survived a
naive any-token-overlap test.  So this GRADES a match instead of accepting it,
and only trusts an id when the surname AND a given name both agree.

**Everything weaker is a judgement call, not an error.**  Real rosters produce
one-word form names, married names, transliteration variants, and given names
written as initials.  The tool's job is to sort those into buckets and hand the
short list to a human, not to reject them.
"""
from __future__ import annotations

import math
import re

# --- ranks ------------------------------------------------------------------

RANK_RE = re.compile(r"\s*(\d+)\s*([dDkK])")


def rank_to_stones(rank_str):
    """'2k' -> -1, '1k' -> 0, '1d' -> 1, '5d' -> 5.  None if unparseable.

    The AGA scale has no zero rung, so this is the index that makes "one rank"
    mean one everywhere.
    """
    if not rank_str:
        return None
    m = RANK_RE.match(str(rank_str))
    if not m:
        return None
    n, letter = int(m.group(1)), m.group(2).lower()
    if n > 40 or n < 1:
        # Nobody is 41k.  A stray year or an AGA id landed in the rank field.
        return None
    return n if letter == "d" else 1 - n


def stones_to_rank(stones):
    if stones is None:
        return ""
    return f"{stones}d" if stones >= 1 else f"{1 - stones}k"


def rating_to_stones(rating):
    """AGA float rating -> stone index, by TRUNCATION toward zero.

    4.98811 is a 4d.  This is the hard rule, not a rounding preference: the AGA
    scale is continuous and skips the open interval (-1, 1).
    """
    if rating is None:
        return None
    if rating >= 1:
        return int(math.floor(rating))
    if rating <= -1:
        return 1 - int(math.floor(abs(rating)))
    return None                      # inside the excluded band; should not occur


def rating_to_rank(rating):
    return stones_to_rank(rating_to_stones(rating))


# --- names ------------------------------------------------------------------

def name_tokens(s):
    """Lowercase alphabetic tokens of length 2+.

    Single letters are dropped on purpose.  A form name of "R Aldergate" or a
    TDList "Yu, Harvy(Chengxi)" should compare on the parts that carry identity;
    an initial matches far too much to be evidence of anything.  The cost is that
    a player who registers with an initial for a given name can only ever be
    matched on the other half -- which is exactly what the ONEWORD grade says.
    """
    return {t for t in re.split(r"[^A-Za-z]+", str(s or "").lower()) if len(t) > 1}


def split_tdlist_name(tdlist_name):
    """'Last, First M' -> (surname tokens, given-name tokens).

    The AGA writes "Yu, Harvy(Chengxi)" and "Chen, ZhaoNian", so the given half
    is tokenized rather than taken whole.  A record with no comma (rare, but
    present) puts everything in the given half rather than guessing which is
    which.
    """
    raw = str(tdlist_name or "")
    if "," in raw:
        last, _, first = raw.partition(",")
        return name_tokens(last), name_tokens(first)
    return set(), name_tokens(raw)


# --- grading an id ----------------------------------------------------------

FULL      = "full"       # surname + given name both agree
LAST      = "last"       # surname agrees, given name does not
FIRST     = "first"      # given name agrees, surname does not
ONEWORD   = "oneword"    # only one half of the form name is usable
NONE      = "none"       # no overlap at all
NOT_FOUND = "notfound"   # the id belongs to no AGA member
NO_ID     = "noid"       # no id on the form

#: Grades that need a human to look, worst first, with why it matters.
NEEDS_A_LOOK = [
    (NOT_FOUND, "AGA ID MATCHES NO MEMBER"),
    (NONE,      "AGA ID BELONGS TO SOMEONE ELSE"),
    (FIRST,     "SURNAME DISAGREES - given name only"),
    (LAST,      "GIVEN NAME DISAGREES - surname only"),
]


def grade_aga_id(form_name, aga_id, tdlist):
    """How much does the AGA record this id points at look like this player?

    Returns (grade, tdlist_name, detail).  The form name is free text, so the
    surname is not positionally identifiable: both halves of the AGA record are
    compared against the whole token set instead of assuming word order.
    """
    if not aga_id:
        return NO_ID, "", "no AGA id on the form"
    rec = tdlist.get(str(aga_id))
    if not rec:
        return NOT_FOUND, "", "no AGA member has this id"

    form = name_tokens(form_name)
    last, first = split_tdlist_name(rec["name"])
    hit_last, hit_first = bool(form & last), bool(form & first)

    if hit_last and hit_first:
        return FULL, rec["name"], "surname + given name agree"
    if len(form) < 2:
        # One usable token -- "Jake", or "V Lewis" where the initial was dropped.
        # It can only ever match one half, so a half match is not a smell.
        which = "given name" if hit_first else ("surname" if hit_last else "nothing")
        return (ONEWORD if (hit_first or hit_last) else NONE), rec["name"], \
               f"form name has one usable token; matches {which}"
    if hit_last:
        return LAST, rec["name"], "surname agrees, GIVEN NAME does not"
    if hit_first:
        return FIRST, rec["name"], "given name agrees, SURNAME does not"
    return NONE, rec["name"], "no part of the name agrees"


def digit_typo(a, b):
    """Describe how two ids differ, when they plausibly differ by a slip."""
    a, b = str(a), str(b)
    if len(a) != len(b):
        return ""
    diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    if len(diff) == 1:
        return "1 digit different"
    if len(diff) == 2 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]]:
        return "2 digits transposed"
    return f"{len(diff)} digits different" if diff else ""


def suggest_aga_id(form_name, requested_rank, tdlist, limit=3):
    """Find the record a mistyped id was probably meant to point at.

    Reporting "this id is wrong" without "and here is the right one" leaves the
    actual work undone -- and in practice the right record is one name lookup
    away, because the mistakes are single-digit slips.

    Requires BOTH a surname and a given name to match (>= 2 shared tokens), which
    is what keeps a common surname from dragging in thirty candidates, then ranks
    what survives by how well each record's rating agrees with the rank the
    player claimed.  Returns [(aga_id, record, stone_gap_or_None)].
    """
    want = name_tokens(form_name)
    if len(want) < 2:
        return []
    req = rank_to_stones(requested_rank)

    out = []
    for aga_id, rec in tdlist.items():
        if len(want & name_tokens(rec["name"])) < 2:
            continue
        gap = None
        if req is not None:
            got = rating_to_stones(rec.get("rating"))
            if got is not None:
                gap = abs(req - got)
        out.append((gap if gap is not None else 99, aga_id, rec, gap))
    out.sort(key=lambda t: (t[0], t[1]))
    return [(i, r, g) for _, i, r, g in out[:limit]]


# --- rank policy ------------------------------------------------------------

AUTO_DENY   = "auto-deny"     # one step up: not adjudicated, just refused
ADJUDICATE  = "adjudicate"    # two or more steps: the only real TD decision
DENY_DOWN   = "deny-down"     # asking for a demotion
AT_BOOK     = "at-book"       # asking for the rank they already hold


def grade_rank_ask(asked, rating):
    """Compare a declared rank against the book.  Returns (verdict, steps).

    Measured in RANK STEPS, never rating delta.  A delta threshold is wrong in
    both directions: it misses +1.74 asking 2d (a full rank on a delta of 0.26)
    and flags -4.95 asking 4k (no promotion at all, on a delta of 0.95).
    """
    want = rank_to_stones(asked)
    book = rating_to_stones(rating)
    if want is None or book is None:
        return None, None
    steps = want - book
    if steps <= -1:
        return DENY_DOWN, steps
    if steps == 0:
        return AT_BOOK, 0
    return (AUTO_DENY if steps == 1 else ADJUDICATE), steps


# --- the rating list --------------------------------------------------------

def load_tdlist(path):
    """AGA id -> record, from a TDList variant A file (9 tab-separated columns).

    Members with no rating on file are kept, with rating None: they are real
    people who need a rank decision, they are just not rated yet.
    """
    out = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            f = line.rstrip("\n").split("\t")
            if len(f) < 9 or not f[1].strip():
                continue
            try:
                rating = float(f[3])
            except ValueError:
                rating = None
            out[f[1].strip()] = {
                "name": f[0].strip(), "aga_id": f[1].strip(), "membership": f[2].strip(),
                "rating": rating, "expires": f[4].strip(), "club": f[5].strip(),
                "state": f[6].strip(), "sigma": f[7].strip(), "last_game": f[8].strip(),
            }
    return out
