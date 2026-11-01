"""Contextual memory: per-person conversation history and learned facts (SQLite)."""
from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path
from typing import Dict, List

_FACT_PATTERNS = [
    ("name", re.compile(r"\bmy name is ([A-Za-z]+)", re.I)),
    ("likes", re.compile(r"\bi (?:really )?(?:like|love|enjoy) ([^.!?,]{2,40})", re.I)),
    ("job", re.compile(r"\bi(?:'m| am) (?:a|an) ([^.!?,]{2,30})", re.I)),
    ("city", re.compile(r"\bi(?:'m| am) from ([A-Za-z ]{2,30})", re.I)),
]


class Memory:
    def __init__(self, path: str = "data/memory.db") -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS turns(id INTEGER PRIMARY KEY, person TEXT, role TEXT, text TEXT, ts REAL);
            CREATE TABLE IF NOT EXISTS facts(person TEXT, key TEXT, value TEXT, ts REAL, PRIMARY KEY(person, key, value));
        """)

    def add_turn(self, person: str, role: str, text: str) -> None:
        self.db.execute("INSERT INTO turns(person, role, text, ts) VALUES (?,?,?,?)",
                        (person, role, text, time.time()))
        if role == "user":
            self._learn(person, text)
        self.db.commit()

    def _learn(self, person: str, text: str) -> None:
        for key, pat in _FACT_PATTERNS:
            m = pat.search(text)
            if m:
                self.db.execute("INSERT OR REPLACE INTO facts VALUES (?,?,?,?)",
                                (person, key, m.group(1).strip(), time.time()))

    def recent(self, person: str, n: int = 8) -> List[Dict[str, str]]:
        rows = self.db.execute(
            "SELECT role, text FROM turns WHERE person=? ORDER BY id DESC LIMIT ?", (person, n)).fetchall()
        return [{"role": r, "content": t} for r, t in reversed(rows)]

    def facts(self, person: str) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {}
        for k, v in self.db.execute("SELECT key, value FROM facts WHERE person=? ORDER BY ts", (person,)):
            out.setdefault(k, []).append(v)
        return out

    def facts_text(self, person: str) -> str:
        f = self.facts(person)
        return "; ".join(f"{k}: {', '.join(v)}" for k, v in f.items()) or "nothing yet"
