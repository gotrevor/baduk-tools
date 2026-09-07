#!/usr/bin/env python3
"""Where does a player stand among everyone else at their rank?

Reads the AGA TDList - the rating list every tournament director already
downloads - and reports a player's position inside their own rank band.

    python3 aga-rank.py tdlist.tsv --fetch          # download today's list
    python3 aga-rank.py tdlist.tsv "Steinberg"      # by name (substring)
    python3 aga-rank.py tdlist.tsv 17531            # by AGA ID
    python3 aga-rank.py tdlist.tsv 17531 --pool all # compare against every rated player

By default the comparison pool is players who have played a rated game in the
last 5 years - see --pool and --years.

Public domain / CC0.  Python 3.9+, standard library only.
"""

import argparse
import csv
import datetime
import math
import re
import sys
import urllib.request

# The AGA's stable handle for the tab-separated "A" variant of the list.  It is
# NOT an HTTP redirect: usgo.org serves a page carrying a JavaScript redirect to
# an Azure host whose name changes, so resolve it at runtime rather than pasting
# the Azure URL anywhere.  That host also rejects a default urllib User-Agent.
HANDLE = "https://www.usgo.org/TDListA"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def get(url, timeout=90):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=timeout).read()


def fetch(path):
    page = get(HANDLE, timeout=30).decode("utf-8", "replace")
    m = re.search(r"""https://[^\s'"]*GenerateTDList[A-Z]?""", page)
    if not m:
        sys.exit("no GenerateTDList URL found on " + HANDLE)
    data = get(m.group(0))
    if len(data) < 100_000:          # a real list is ~1 MB; smaller means error page
        sys.exit("suspiciously small download (%d bytes)" % len(data))
    open(path, "wb").write(data)
    print("wrote %s (%.1f MB) from %s" % (path, len(data) / 1e6, m.group(0)))


def rank_of(rating):
    """AGA rating -> rank string.  Truncates toward zero: 4.99 is a 4d, not a 5d.
    The scale has no 0: ratings run ... -2 (2k) -1 (1k) | 1 (1d) 2 (2d) ..."""
    n = math.trunc(rating)
    return "%dd" % n if rating > 0 else "%dk" % -n


def parse_date(text):
    """m/d/yyyy -> date, or None when the field is blank or malformed."""
    try:
        month, day, year = (int(x) for x in text.strip().split("/"))
        return datetime.date(year, month, day)
    except ValueError:
        return None


def load(path):
    """Every row of the TDList that carries a rating.

    Columns, tab-separated, no header:
      0 name "Last, First"   3 rating              6 state
      1 AGA id               4 membership expires  7 sigma
      2 membership type      5 chapter code        8 date of last rated game

    A blank rating means the player joined but has never played a rated game -
    those rows are not players in this sense, so drop them."""
    out = []
    for row in csv.reader(open(path, encoding="utf-8", errors="replace"), delimiter="\t"):
        if len(row) < 9 or not row[3].strip():
            continue
        try:
            rating = float(row[3])
        except ValueError:
            continue
        out.append({"name": row[0], "id": row[1], "rating": rating,
                    "expires": parse_date(row[4]), "last_game": parse_date(row[8])})
    return out


def active(players, pool, years):
    """The comparison pool.  "The country" is 15,000 people the AGA has ever
    rated, two thirds of whom last played before 2010, so pick who counts:
    'active' is anyone with a rated game inside `years`, 'all' is everybody.
    (Membership expiry would be a proxy for the same thing, and a worse one:
    it admits 1,000-odd people who pay dues but do not play.)"""
    if pool == "all":
        return players
    cutoff = datetime.date.today() - datetime.timedelta(days=365 * years)
    return [p for p in players if p["last_game"] and p["last_game"] >= cutoff]


def report(players, who, pool="active", years=5):
    peers_pool = active(players, pool, years)
    hits = [p for p in players
            if p["id"] == who or who.lower() in p["name"].lower()]
    if not hits:
        sys.exit("no player matching %r" % who)
    label = ("ever rated" if pool == "all"
             else "played in the last %d years" % years)
    for p in hits:
        band = rank_of(p["rating"])
        peers = sorted(q["rating"] for q in peers_pool if rank_of(q["rating"]) == band)
        print("%s (%s)  %.5f  %s   [pool: %s, %d players]"
              % (p["name"], p["id"], p["rating"], band, label, len(peers_pool)))
        if p["rating"] not in peers:
            print("   not in the pool himself - last rated game %s, membership expires %s"
                  % (p["last_game"], p["expires"]))
            continue
        pos = peers.index(p["rating"]) + 1               # 1 = weakest in the band
        weaker = sum(1 for q in peers_pool if q["rating"] < p["rating"])
        print("   #%d of %d %s players from the bottom (#%d from the top)"
              % (pos, len(peers), band, len(peers) - pos + 1))
        print("   stronger than %d of %d (%.1f%%)"
              % (weaker, len(peers_pool), 100.0 * weaker / len(peers_pool)))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tdlist", help="path to a TDList .tsv snapshot")
    ap.add_argument("player", nargs="?", help="AGA id, or part of a name")
    ap.add_argument("--fetch", action="store_true", help="download a fresh list to TDLIST first")
    ap.add_argument("--pool", choices=("active", "all"), default="active",
                    help="who counts as a player (default: active)")
    ap.add_argument("--years", type=int, default=5, metavar="N",
                    help="how recent the pool has to be (default: 5)")
    a = ap.parse_args()
    if a.fetch:
        fetch(a.tdlist)
    if a.player:
        report(load(a.tdlist), a.player, a.pool, a.years)


if __name__ == "__main__":
    main()
