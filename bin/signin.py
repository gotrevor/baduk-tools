"""The check-in sheet: a printed page with a box for each player to initial.

Yes, printed.  Many tournaments take results and check-in electronically, and
that is fine - but a sheet of paper with a person's own initials on it is the
only record that survives a laptop dying, a spreadsheet being edited, or a
disagreement about who was actually in the room for round 3.  It is the same
argument as a voter-verifiable paper trail: the electronic system is the fast
path, the paper is the one you can hold up afterwards.  Keep both.

Two layout decisions that are not arbitrary:

**Sorted by LAST NAME**, always.  The published standings sort by strength, which
is the wrong order for a person standing at a desk looking for their own name.

**Pages split EVENLY.**  80 players over 3 pages is 27/27/26, not 30/30/20.
Filling each page to capacity looks like the sheet ran out rather than like a set
of sheets, and it puts three times as many people in the line at the first page.
"""
from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

#: OpenGotha's placeholder for "this player named no club".  It is not a club
#: code - it appears nowhere in the AGA TDList - so printing it raw makes
#: everyone who skipped the field look like a member of a club called NoCb.
OG_NO_CLUB = "NoCb"
OG_NO_CLUB_DISPLAY = "n/a"

#: A withdrawal convention some registration sheets use: rank set to 99k.
WITHDRAWN_RANK = "99k"

CHROMES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]


def normalize_rank(rank_str):
    """'4D' -> '4d', ' 9K ' -> '9k', '01d' -> '1d'.  Unparseable passes through."""
    s = re.sub(r"\s+", " ", str(rank_str or "")).strip()
    m = re.match(r"^0*(\d+)\s*([dDkK])\b", s)
    return f"{int(m.group(1))}{m.group(2).lower()}" if m else s


def split_name(full, fallback=""):
    """(last, first) from an AGA 'Last, First M' record, or from free text.

    A form name is free text - "Jake", "wei chen", "Harvy Chengxi Yu" - so the
    fallback splits on the LAST whitespace token, and a one-word name becomes the
    LAST name, because that is what the desk will search on.
    """
    full = (full or "").strip()
    if "," in full:
        last, _, first = full.partition(",")
        return last.strip(), first.strip()
    name = re.sub(r"\s+", " ", str(full or fallback or "")).strip()
    if not name:
        return "", ""
    parts = name.split(" ")
    if len(parts) == 1:
        return parts[0], ""
    return parts[-1], " ".join(parts[:-1])


def rows_from_registrations(people, tdlist=None):
    """(rows, withdrawn count) from registration rows, sorted by last name.

    Prefers the AGA record's spelling when the id resolved, because it is already
    "Last, First" and it is the name on the player's own membership.
    """
    tdlist = tdlist or {}
    out, dropped = [], 0
    for r in people:
        if normalize_rank(r.get("asked")).lower() == WITHDRAWN_RANK:
            dropped += 1
            continue
        rec = tdlist.get(str(r.get("aga_id") or ""))
        last, first = split_name((rec or {}).get("name", ""), r.get("name", ""))
        out.append({"aga_id": r.get("aga_id", ""), "last": last, "first": first,
                    "rank": normalize_rank(r.get("asked")),
                    "club": (rec or {}).get("club"), "note": ""})
    out.sort(key=lambda r: (r["last"].lower(), r["first"].lower()))
    return out, dropped


def rows_from_opengotha(path, rnd, add=(), drop=(), notes=None):
    """(rows, forced, saved-stamp) from the LIVE tournament file, for one round.

    Mid-tournament this is the only honest source: `participating` carries who is
    still here, and a registration list knows nothing about it - it would happily
    print a player who left after round 2.  `add`/`drop` are AGA ids that override
    the flag, and the caller is told which were forced, so an override is visible
    rather than silent.
    """
    notes = notes or {}
    add, drop = set(map(str, add)), set(map(str, drop))
    root = ET.parse(path).getroot()
    rows, forced = [], []
    for pl in root.find("Players"):
        d = pl.attrib
        aid = str(d.get("agaId", "")).strip()
        flags = d.get("participating", "")
        playing = len(flags) >= rnd and flags[rnd - 1] == "1"
        if aid in drop:
            continue
        if not playing and aid not in add:
            continue
        if not playing:
            forced.append(f"{d.get('name','')}, {d.get('firstName','')}")
        rows.append({"aga_id": aid,
                     "last": (d.get("name") or "").strip(),
                     "first": (d.get("firstName") or "").strip(),
                     "rank": normalize_rank(d.get("rank", "")),
                     "club": (d.get("club") or "").strip(),
                     "note": notes.get(aid, "")})
    rows.sort(key=lambda r: (r["last"].lower(), r["first"].lower()))
    saved = root.get("saveDT", "")
    stamp = (f"{saved[:4]}-{saved[4:6]}-{saved[6:8]} {saved[8:10]}:{saved[10:12]}"
             if len(saved) >= 12 else "unknown")
    return rows, forced, stamp


CSS = """
  @page { size: letter portrait; margin: 0.45in 0.5in 0.4in 0.5in; }
  * { box-sizing: border-box; }
  body { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
         color: #111; margin: 0; }
  .page { page-break-after: always; }
  .page:last-child { page-break-after: auto; }
  h1 { font-size: 15pt; margin: 0; }
  .sub { font-size: 9pt; color: #555; margin: 2pt 0 8pt 0; }
  table { border-collapse: collapse; width: 100%; font-size: 11pt; }
  th, td { border: 0.5pt solid #999; padding: 3pt 6pt; text-align: left; }
  thead th { font-size: 8pt; line-height: 1.15; border-bottom: 1.6pt solid #000;
             text-transform: uppercase; letter-spacing: .03em; vertical-align: bottom; }
  tbody tr { height: __ROWH__in; page-break-inside: avoid; }
  td.id { text-align: right; font-variant-numeric: tabular-nums; color: #444;
          font-size: 9.5pt; }
  td.last { font-weight: 700; }
  td.rank { text-align: center; font-weight: 700; }
  th.box, td.box { background: #fff; }
  td.club { text-align: center; font-size: 9.5pt; }
  td.club.none { color: #666; }
  td.note { font-size: 8pt; font-style: italic; }
  .pageno { font-size: 8.5pt; text-align: center; margin-top: 7pt; }
"""

# Inches of body left on a Letter page once the margins, the heading block and
# the column header have taken their share - measured off a real render, so
# re-measure if any of those change.  Rows then stretch to fill it (capped, so a
# 12-player list does not get 1-inch rows), which is what stops the last page
# ending in half a page of white.
BODY_INCHES = 9.05        # overflows just past 9.20 in a real render
ROW_MIN_IN = 0.28         # tightest legible row -> how many fit on a page
ROW_MAX_IN = 0.42         # roomiest useful row -> stops a short list ballooning
PAGENO_INCHES = 0.32      # centred "page x of y" block + its margin
ROWS_PER_PAGE = int((BODY_INCHES - PAGENO_INCHES) / ROW_MIN_IN)


def page_split(n, per_page=ROWS_PER_PAGE):
    """Row counts per page, as EVEN as they divide.  80 over 3 pages -> 27/27/26."""
    if n <= 0:
        return []
    pages = max(1, -(-n // per_page))
    base, rem = divmod(n, pages)
    return [base + (1 if i < rem else 0) for i in range(pages)]


def render_html(rows, title, subtitle):
    e = html.escape
    wide = any(r.get("club") is not None for r in rows)
    if wide:
        heads = ('<th style="width:0.65in">AGA<br>Id</th>'
                 '<th style="width:1.65in">Last name</th>'
                 '<th style="width:1.45in">First name</th>'
                 '<th style="width:0.55in">Rank</th>'
                 '<th style="width:0.65in">Club</th>'
                 # Narrow: it holds two or three pen strokes.  The instruction
                 # lives in the subtitle, so the head need not carry it.
                 '<th class="box" style="width:0.6in">Initial</th>'
                 '<th>Notes / withdrawing?</th>')
    else:
        heads = ('<th style="width:0.7in">AGA<br>Id</th>'
                 '<th style="width:1.9in">Last name</th>'
                 '<th style="width:1.7in">First name</th>'
                 '<th style="width:0.6in">Rank</th>'
                 '<th class="box">Initial that you\'re here</th>')

    counts = page_split(len(rows))
    # One row height for every page, driven by the FULLEST one, so the sheets look
    # like a set rather than three different documents.  The centred page-number
    # block eats the same budget: leave it out of the arithmetic and every page
    # overflows its footer onto a blank sheet, doubling the print job.
    body_in = BODY_INCHES - (PAGENO_INCHES if len(counts) > 1 else 0)
    row_h = min(ROW_MAX_IN, body_in / max(counts or [1]))
    css = CSS.replace("__ROWH__", f"{row_h:.3f}")

    pages, i = [], 0
    for pno, count in enumerate(counts, 1):
        body = []
        for r in rows[i:i + count]:
            cells = ["<tr>",
                     f'<td class="id">{e(str(r["aga_id"]))}</td>',
                     f'<td class="last">{e(r["last"])}</td>',
                     f'<td>{e(r["first"])}</td>',
                     f'<td class="rank">{e(r["rank"])}</td>']
            if wide:
                club = (r.get("club") or "").strip()
                none = club in ("", OG_NO_CLUB)
                shown = OG_NO_CLUB_DISPLAY if none else club
                cells.append(f'<td class="club{" none" if none else ""}">{e(shown)}</td>')
            cells.append('<td class="box"></td>')          # initial, left of notes
            if wide:
                cells.append(f'<td class="note">{e(r.get("note") or "")}</td>')
            cells.append("</tr>")
            body.append("".join(cells))
        i += count
        # Page number at the FOOT, centred: in the subtitle it competes with what
        # someone actually reads before searching the list.
        of = (f'<div class="pageno">page {pno} of {len(counts)}</div>'
              if len(counts) > 1 else "")
        pages.append(f"""<div class="page">
<h1>{e(title)}</h1>
<p class="sub">{subtitle}</p>
<table>
<thead><tr>{heads}</tr></thead>
<tbody>
{chr(10).join(body)}
</tbody>
</table>
{of}
</div>""")

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{e(title)}</title>
<style>{css}</style></head><body>
{chr(10).join(pages)}
</body></html>
"""


def to_pdf(html_text, pdf_path: Path):
    """Render via headless Chrome.  Leaves the intermediate HTML beside the PDF."""
    chrome = next((c for c in CHROMES if os.path.exists(c)), None) or shutil.which("chromium")
    if not chrome:
        sys.exit("no Chrome/Chromium found for PDF rendering; "
                 "the HTML was written beside the requested PDF - print that")
    tmp = pdf_path.with_suffix(".html")
    tmp.write_text(html_text)
    subprocess.run([chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf_path}", tmp.as_uri()],
                   check=True, capture_output=True)
    return pdf_path
