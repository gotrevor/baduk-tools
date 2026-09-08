"""Online-Go (OGS) lookups, for cross-checking a player's claimed strength.

Useful when a registrant has no AGA rating yet but does play online: their OGS
rank is evidence for an entry rank.  Treat it as evidence, not as an answer --
the two scales are fitted to different populations and drift apart at the ends.

Two things here were learned the hard way and are worth keeping:

**The widely-quoted OGS constants are wrong.**  `850 / 0.032` puts a 24k player
at 38k and an AGA 2d at 4k.  Fitted against OGS's own `ranking` field over 15
accounts, the actual relation is `rating = 525 * exp(0.04319654 * ranking)`, with
a maximum residual of 0.000000 ranking units.  Prefer the `ranking` OGS serves
over deriving one anyway: it is authoritative and it applies OGS's 25k display
floor.

**Never fuzzy-match a handle.**  A near-miss on OGS is a DIFFERENT PERSON:
'kelu' does not exist while 'Kelu' does, at about 22k, and the player being
looked up was an AGA 2d.  Publishing a stranger's rating beside someone's name is
worse than publishing a blank.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

API = "https://online-go.com/api/v1/players/"
USER_AGENT = "baduk-tools/1.0 (+https://github.com/gotrevor/baduk-tools)"
CACHE_HOURS = 24

#: Above this rating deviation OGS itself treats the rating as unsettled.
PROVISIONAL_DEVIATION = 100.0

#: Fitted, not folklore.  See the module docstring.
C, A = 525.0, 0.04319654


def ranking_from_rating(rating):
    if not rating or rating <= 0:
        return None
    return math.log(rating / C) / A


def rank_str(ranking):
    """OGS `ranking` -> rank string.  ranking 30 = 1d, 29 = 1k."""
    if ranking is None:
        return ""
    return f"{ranking - 29:.1f}d" if ranking >= 30 else f"{30 - ranking:.1f}k"


def rank_stones(ranking):
    """OGS ranking -> the same linear stone index AGA ranks use."""
    if ranking is None:
        return None
    return ranking - 29 if ranking >= 30 else 1 - (30 - ranking)


# --- cache ------------------------------------------------------------------

def load_cache(path: Path):
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def save_cache(path: Path, cache):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, sort_keys=True))


# --- lookup -----------------------------------------------------------------

def lookup(session, handle):
    """Resolve one OGS handle to a rating record, or None.

    Exact match first.  OGS's ?username= filter is CASE SENSITIVE and it rejects
    username__iexact, so the fallback is username__istartswith, accepting only a
    genuine case-insensitive exact hit -- never a prefix.
    """
    r = session.get(API, params={"username": handle}, timeout=25)
    r.raise_for_status()
    data = r.json()
    if not data.get("count"):
        r = session.get(API, params={"username__istartswith": handle}, timeout=25)
        r.raise_for_status()
        cands = [p for p in r.json().get("results", [])
                 if p.get("username", "").lower() == handle.lower()]
        if len(cands) != 1:
            return None
        p = cands[0]
    else:
        p = data["results"][0]

    overall = (p.get("ratings") or {}).get("overall") or {}
    if not overall.get("rating"):
        return None
    ranking = p.get("ranking")
    if not isinstance(ranking, (int, float)):
        ranking = ranking_from_rating(overall["rating"])
    return {
        "ogs_id": p.get("id"),
        "username": p.get("username"),
        "rating": overall["rating"],
        "ranking": ranking,
        "deviation": overall.get("deviation"),
        "provisional": bool((overall.get("deviation") or 0) > PROVISIONAL_DEVIATION),
    }


def fetch(handles, cache_path: Path, refresh=False, session=None, log=print):
    """Look up handles, honouring a 24h cache.  Returns (results, misses).

    A network failure keeps the previous good value rather than blanking the
    column: a stale rating is information, an empty cell is not.
    """
    if session is None:
        import requests
        session = requests.Session()
        session.headers["User-Agent"] = USER_AGENT

    cache = load_cache(cache_path)
    now = time.time()
    results, misses = {}, []
    for handle in handles:
        key = handle.lower()
        entry = cache.get(key)
        fresh = (entry and not refresh
                 and (now - entry.get("fetched_at", 0)) / 3600.0 < CACHE_HOURS)
        if fresh:
            (results.__setitem__(handle, entry["player"]) if entry.get("found")
             else misses.append(handle))
            continue
        try:
            player = lookup(session, handle)
        except Exception as e:
            log(f"   ⚠️  OGS lookup failed for {handle!r}: {e}")
            if entry and entry.get("found"):
                results[handle] = entry["player"]
            continue
        cache[key] = {"fetched_at": now, "found": bool(player),
                      "player": player, "handle": handle}
        if player:
            results[handle] = player
        else:
            misses.append(handle)
    save_cache(cache_path, cache)
    return results, misses
