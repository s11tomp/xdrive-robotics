"""Where the host tools write: logs/ under the working directory, and logs/actions.jsonl, one JSON line per
action a tool took on a board (idle, set_config, calibrate, flash, ...). Also reads the tools' CSV logs back.

Paths are relative to the working directory at the time of the call, and logs/ is created on first use.
"""
from __future__ import annotations

import csv
import json
import pathlib
from typing import Any

import numpy as np


def logs_dir() -> pathlib.Path:
    """logs/ under the working directory, created if missing."""
    path = pathlib.Path.cwd() / "logs"
    path.mkdir(exist_ok=True)
    return path


def rel(path: pathlib.Path) -> str:
    """The path relative to the working directory, for messages and log records."""
    return str(path.relative_to(pathlib.Path.cwd()))


def log_action(record: dict[str, Any]) -> None:
    """Appends the record to logs/actions.jsonl as one JSON line."""
    with (logs_dir() / "actions.jsonl").open("a") as f:
        f.write(json.dumps(record) + "\n")


def read_columns(path: str | pathlib.Path) -> dict[str, np.ndarray]:
    """A tool's CSV log by column: rows whose first cell starts with '#' (metadata) are skipped, the first other
    row names the columns. A numeric column becomes a float array (True/False as 1/0); a column with any other
    text (the bench tools' event column) stays a str array."""
    with open(path, newline="") as f:
        rows = [r for r in csv.reader(f) if r and not r[0].startswith("#")]
    header, data = rows[0], rows[1:]
    out: dict[str, np.ndarray] = {}
    for i, name in enumerate(header):
        cells = [r[i] for r in data]
        try:
            out[name] = np.array([1.0 if c == "True" else 0.0 if c == "False" else float(c) for c in cells])
        except ValueError:
            out[name] = np.array(cells)
    return out
