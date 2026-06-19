#!/usr/bin/env python3
"""WSAI portfolio MCP server — cross-repo status, translation gap, card search."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path

from mcp.server.fastmcp import FastMCP

HOME = Path(os.environ.get("USERPROFILE", Path.home()))
CARD_DB = Path(os.environ.get("WS_CARD_DB", HOME / "ws-card-db"))
SIM_LOGGER = Path(os.environ.get("WS_SIM_LOGGER", HOME / "ws-sim-logger"))
SIM_AI = Path(os.environ.get("WS_SIM_AI", HOME / "ws-sim-ai"))

REPOS = {
    "ws-card-db": CARD_DB,
    "ws-sim-logger": SIM_LOGGER,
    "ws-sim-ai": SIM_AI,
}

mcp = FastMCP("ws-tools")


def _read_status(repo_path: Path) -> str:
    p = repo_path / "STATUS.md"
    if not p.is_file():
        return f"(no STATUS.md at {p})"
    return p.read_text(encoding="utf-8")


@mcp.tool()
def get_portfolio_status(project: str = "") -> str:
    """Return STATUS.md for one repo (ws-card-db, ws-sim-logger, ws-sim-ai) or all three."""
    key = project.strip().lower()
    if key:
        for name, path in REPOS.items():
            if key in name or key.replace("_", "-") in name:
                return f"# {name}\n\n{_read_status(path)}"
        return f"Unknown project '{project}'. Use: ws-card-db, ws-sim-logger, ws-sim-ai"
    parts = []
    for name, path in REPOS.items():
        parts.append(f"{'=' * 60}\n# {name}\n{'=' * 60}\n\n{_read_status(path)}")
    return "\n\n".join(parts)


@mcp.tool()
def get_translation_gap() -> str:
    """Summarize bilingual translation batch progress from pipeline/_tr_manifest.json."""
    manifest = CARD_DB / "pipeline" / "_tr_manifest.json"
    if not manifest.is_file():
        return "No _tr_manifest.json — run: python pipeline/_tr_extract.py"

    batches = json.loads(manifest.read_text(encoding="utf-8"))
    by_kind: dict[str, dict[str, int]] = {}
    missing: list[str] = []

    for entry in batches:
        kind = entry.get("kind", "?")
        out_path = Path(entry["out"])
        done = out_path.is_file()
        stats = by_kind.setdefault(kind, {"total": 0, "done": 0, "strings": 0})
        stats["total"] += 1
        stats["strings"] += entry.get("n", 0)
        if done:
            stats["done"] += 1
        else:
            missing.append(out_path.name)

    lines = ["# Translation batch progress", ""]
    for kind, s in sorted(by_kind.items()):
        lines.append(f"- **{kind}**: {s['done']}/{s['total']} batches done ({s['strings']} strings in manifest)")
    if missing:
        lines.append("")
        lines.append("**Missing outputs:**")
        for name in missing[:30]:
            lines.append(f"- {name}")
        if len(missing) > 30:
            lines.append(f"- … and {len(missing) - 30} more")
    lines.append("")
    lines.append("Resume: merge `.out.json` → `abilities_tr.json` / `name_tr.json` / `trait_tr.json`, then `python pipeline/build_db.py`")
    return "\n".join(lines)


@mcp.tool()
def get_logger_version() -> str:
    """Return the injected logger version from ws-sim-logger."""
    logger_cs = SIM_LOGGER / "src" / "WSSimInjected" / "Logger.cs"
    if not logger_cs.is_file():
        return f"Logger.cs not found at {logger_cs}"
    text = logger_cs.read_text(encoding="utf-8")
    m = re.search(r'Version\s*=\s*"([^"]+)"', text)
    version = m.group(1) if m else "unknown"
    status = _read_status(SIM_LOGGER)
    return f"Logger version: **{version}**\n\n---\n\n{status}"


def _db_path() -> Path | None:
    for candidate in (
        CARD_DB / "site" / "ws.sqlite",
        CARD_DB / "site" / "ws.sqlite.gz",
    ):
        if candidate.suffix == ".sqlite" and candidate.is_file():
            return candidate
    return None


@mcp.tool()
def search_cards(query: str, limit: int = 10) -> str:
    """Search cards by card number, name, or ability text (requires site/ws.sqlite)."""
    db_file = _db_path()
    if db_file is None:
        return (
            "site/ws.sqlite not found. Build it first:\n"
            "  cd ws-card-db && python pipeline/build_db.py"
        )
    limit = max(1, min(limit, 50))
    q = f"%{query.strip()}%"
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT c.card_number, c.name, c.name_en, c.type, c.level, c.cost, c.power, c.soul
            FROM cards c
            WHERE c.card_number LIKE ? OR c.name LIKE ? OR c.name_en LIKE ?
               OR EXISTS (
                    SELECT 1 FROM abilities a
                    WHERE a.card_number = c.card_number
                      AND (a.jp_text LIKE ? OR a.en_text LIKE ?)
               )
            LIMIT ?
            """,
            (q, q, q, q, q, limit),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return f"No cards matching '{query}'."
    lines = [f"# Cards matching '{query}' ({len(rows)} shown)", ""]
    for r in rows:
        name = r["name_en"] or r["name"]
        lines.append(
            f"- **{r['card_number']}** {name} "
            f"({r['type']} L{r['level']}/C{r['cost']} P{r['power']}/S{r['soul']})"
        )
    return "\n".join(lines)


@mcp.tool()
def get_card(card_number: str) -> str:
    """Full card row + abilities for one card_number (requires site/ws.sqlite)."""
    db_file = _db_path()
    if db_file is None:
        return "site/ws.sqlite not found — run pipeline/build_db.py first."
    cn = card_number.strip().upper()
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    try:
        card = conn.execute("SELECT * FROM cards WHERE card_number = ?", (cn,)).fetchone()
        if not card:
            return f"Card not found: {cn}"
        abilities = conn.execute(
            "SELECT * FROM abilities WHERE card_number = ? ORDER BY idx",
            (cn,),
        ).fetchall()
    finally:
        conn.close()

    lines = [f"# {cn}", ""]
    for k in card.keys():
        if card[k] not in (None, ""):
            lines.append(f"- **{k}**: {card[k]}")
    if abilities:
        lines.append("")
        lines.append("## Abilities")
        for a in abilities:
            cost = a["power_cost"]
            conf = a["confidence"] or "?"
            en = a["en_text"] or "(no EN)"
            lines.append(
                f"- [{a['ability_type']}] {a['family']} — cost {cost} ({a['method']}/{conf})\n"
                f"  EN: {en}\n"
                f"  JP: {a['jp_text']}"
            )
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
