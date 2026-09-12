"""Table extraction — task 1.6.

Tables are preserved as tables, with header hierarchy intact (Phase 1 exit
criterion). Flattening a multi-row header loses the column-to-condition mapping,
which is the failure the spec's own P-004 example describes: BLEU values
attributed to the wrong SNR.

Precision over recall, deliberately. PyMuPDF's detector also fires on figure
legends and boxed diagrams, and a figure legend stored as a table would feed
fabricated numbers into the claim store, where they would look exactly like real
ones. A missed table is visible as an absence; a false table is invisible as an
error. So the filters below reject anything that does not clearly look tabular,
and recall is left for the challenger parser to win on.
"""

from __future__ import annotations

import re

import pymupdf

from survey.ingest.model import ParsedTable

# "TABLE I", "Table 2:", "TABLE III." — the caption convention in this corpus.
_CAPTION = re.compile(r"^\s*(TABLE|Table)\s+([IVXLC]+|\d+)\b[.:]?\s*(.*)$")

MIN_ROWS = 2
MIN_COLS = 2
# How far above or below a table's bbox to look for its caption, in points.
CAPTION_SEARCH_PT = 80.0


def _cell_text(cell: str | None) -> str:
    if not cell:
        return ""
    # PyMuPDF returns private-use glyphs ( etc.) for maths in some fonts.
    text = "".join(c for c in cell if not ("" <= c <= ""))
    return " ".join(text.replace("\x00", "").split())


def _looks_tabular(grid_rows: list[list[str]]) -> bool:
    """Reject figure legends and boxed diagrams masquerading as tables.

    The signature of a false positive in this corpus is a 2-row "table" of mostly
    empty cells holding fragments of a diagram label ('UT', 'Transfo', 'rmer').
    Real tables are denser and have more populated columns.
    """
    if len(grid_rows) < MIN_ROWS:
        return False
    cols = max(len(r) for r in grid_rows)
    if cols < MIN_COLS:
        return False

    cells = [c for row in grid_rows for c in row]
    filled = [c for c in cells if c]
    if not cells or len(filled) / len(cells) < 0.5:
        return False

    # A diagram fragment is a couple of rows of debris; a table has body rows.
    if len(grid_rows) < 3 and len(filled) < 6:
        return False

    # Columns that are entirely empty indicate a mis-detected grid.
    empty_cols = sum(
        1
        for i in range(cols)
        if not any(len(r) > i and r[i] for r in grid_rows)
    )
    return empty_cols / cols <= 0.34


def _find_caption(page: pymupdf.Page, bbox: tuple) -> tuple[str | None, str | None]:
    """Return (label, caption) from text near the table, if any.

    Searched above and below: IEEE puts table captions above, most other styles
    below, and both conventions appear in this corpus.
    """
    x0, y0, x1, y1 = bbox
    band = pymupdf.Rect(
        max(x0 - 40, 0), max(y0 - CAPTION_SEARCH_PT, 0), x1 + 40, y1 + CAPTION_SEARCH_PT
    )
    try:
        text = page.get_text("text", clip=band)
    except Exception:
        return None, None

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for i, line in enumerate(lines):
        if m := _CAPTION.match(line):
            label = f"Table {m.group(2)}"
            rest = m.group(3).strip()
            # Captions usually wrap onto the following line.
            if len(rest) < 25 and i + 1 < len(lines):
                nxt = lines[i + 1]
                if not _CAPTION.match(nxt):
                    rest = (rest + " " + nxt).strip()
            return label, (rest or None)
    return None, None


def extract_tables(doc: pymupdf.Document) -> list[ParsedTable]:
    """Find tables in a document, keeping the header row separate from the body."""
    out: list[ParsedTable] = []
    ordinal = 0

    for page_no in range(doc.page_count):
        page = doc[page_no]
        try:
            found = page.find_tables()
        except Exception:
            # A detector crash on one page must not lose the whole paper.
            continue

        for table in found.tables:
            try:
                raw = table.extract()
            except Exception:
                continue

            rows = [[_cell_text(c) for c in row] for row in raw]
            rows = [r for r in rows if any(r)]
            if not _looks_tabular(rows):
                continue

            header_names = []
            if getattr(table, "header", None) is not None:
                header_names = [_cell_text(h) for h in (table.header.names or [])]

            # PyMuPDF repeats the header as the first body row when the header is
            # *inside* the table; drop the duplicate rather than storing it twice.
            body = rows
            if header_names and rows and rows[0] == header_names:
                body = rows[1:]
            if not body:
                continue

            label, caption = _find_caption(page, table.bbox)

            # A single-body-row table is real often enough to keep — "the number
            # of transmitted symbols for one image" is a header and one row — but
            # it is also the shape diagram debris takes. Every genuine one in this
            # corpus is captioned and none of the debris is, so require a caption
            # at that size rather than rejecting or accepting the shape outright.
            if len(body) < 2 and not (label or caption):
                continue

            out.append(
                ParsedTable(
                    ordinal=ordinal,
                    label=label,
                    caption=caption,
                    page=page_no + 1,
                    grid={
                        # Header kept separate from body: flattening it loses the
                        # column-to-condition mapping (spec §3, P-004).
                        "header": header_names,
                        "rows": body,
                        "col_count": max(len(r) for r in body),
                        "row_count": len(body),
                        "bbox": [round(v, 1) for v in table.bbox],
                        "detector": "pymupdf.find_tables",
                    },
                )
            )
            ordinal += 1

    return out
