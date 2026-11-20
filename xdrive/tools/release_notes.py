#!/usr/bin/env python3
"""Print one release's section of CHANGELOG.md: the notes of its GitHub release.

The section starts at the heading `## xdrive-robotics [<version>] - <YYYY-MM-DD>` and ends at the next
`## ` heading. Exits with an error when the section is missing, empty or still dated "Unreleased", so a
release tag without its changelog entry fails CI before anything is published.

Usage (from the repo root):  python xdrive/tools/release_notes.py 1.0.0     (or fw-v1.0.0)
"""
import pathlib
import re
import sys

CHANGELOG = pathlib.Path(__file__).resolve().parents[2] / "CHANGELOG.md"
HEADING = re.compile(r"^## xdrive-robotics \[(?P<version>[^\]]+)\] - (?P<date>\S+)\s*$")


def notes(text, version):
    """Return the body of `version`'s section in a changelog's text; raise ValueError if it isn't releasable."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = HEADING.match(line)
        if not (m and m["version"] == version):
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", m["date"]):
            raise ValueError(f"CHANGELOG.md: {version} is dated {m['date']!r}; give it the release date (YYYY-MM-DD)")
        body = []
        for rest in lines[i + 1:]:
            if rest.startswith("## "):
                break
            body.append(rest)
        text = "\n".join(body).strip()
        if not text:
            raise ValueError(f"CHANGELOG.md: the {version} section is empty")
        return text
    raise ValueError(f"CHANGELOG.md has no '## xdrive-robotics [{version}] - <date>' section")


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: release_notes.py <version>, e.g. 1.0.0")
    try:
        print(notes(CHANGELOG.read_text(), sys.argv[1].removeprefix("fw-v")))
    except ValueError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
