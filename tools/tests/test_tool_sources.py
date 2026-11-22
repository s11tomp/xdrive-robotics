"""Static checks on the host tools' sources: every tool compiles under the repo env's Python, and every
property path a tool names as a string literal exists in the generated xdrive.props.

mypy checks typed handles (odrv.axis0...) but neither string paths ("axis0.encoder.pos_estimate"),
which the bench tools use for CSV columns and settings, nor syntax newer than the env's Python
(mypy accepts nested same-type quotes in f-strings, which Python 3.11 rejects).
"""
import pathlib
import re
import sys

import pytest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
from xdrive.paths import HANDLES  # noqa: E402
from xdrive.props import odrv  # noqa: E402

SOURCES = sorted(p for p in TOOLS.glob("*.py"))
# A quoted dotted path whose first part is a top-level member of the interface ("axis0.", "capture.", ...).
ROOTS = sorted({path.split(".")[0] for path in HANDLES if "." in path})
PATH = re.compile(r"""["']((?:%s)\.[A-Za-z_][\w.]*)["']""" % "|".join(ROOTS))


def functions() -> set[str]:
    out = set()

    def walk(obj: object) -> None:
        for v in vars(obj).values():
            if hasattr(v, "inputs") and hasattr(v, "path"):
                out.add(v.path)
            elif not hasattr(v, "path"):
                walk(v)

    walk(odrv)
    return out


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_tool_compiles(path: pathlib.Path) -> None:
    compile(path.read_text(), str(path), "exec")


def test_string_paths_exist() -> None:
    known = set(HANDLES) | functions()
    missing = {}
    for src in SOURCES:
        for m in PATH.finditer(src.read_text()):
            name = m[1].rstrip(".")
            if not any(k.startswith(name) for k in known):  # the path, or a prefix ("axis0.trap_traj.config.")
                missing.setdefault(src.name, []).append(name)
    assert not missing, f"property paths not in xdrive.props: {missing}"
