"""The firmware's endpoint classification against the interface JSON it embeds.

Two pieces of firmware code read the endpoint table from outside the fibre protocol, and both rely on
the generated code agreeing with the JSON the host reads:
- CAN endpoint access (can_simple.cpp) asks fibre::endpoint_kind(), which src/fibre-cpp/endpoints_template.j2
  generates, whether an ID is a read-only property, a read-write property or a function. A function's
  ID classified as a property would run the function on a read.
- The capture (capture.cpp, Capture::add_channel) finds a property's type by searching the embedded JSON
  for the text `"id":<id>,"type":"`. A different key order or spacing would refuse every channel.

The generated endpoint table (build/autogen/endpoints.hpp) is rendered here with the interface generator,
as the firmware build renders it, so no firmware build is needed.

Run from the repo root: python -m pytest -q tools/tests
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
from typing import Any, Iterator

import pytest

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE.parents[1] / "src"


@pytest.fixture(scope="module")
def endpoints_hpp(tmp_path_factory: pytest.TempPathFactory) -> str:
    """build/autogen/endpoints.hpp, rendered as the firmware build renders it."""
    out = tmp_path_factory.mktemp("autogen") / "endpoints.hpp"
    subprocess.run([sys.executable, "-B", "../tools/codegen/interface_generator.py", "--definitions",
                    "odrive-interface.yaml", "--generate-endpoints", "ODrive3",
                    "--template", "fibre-cpp/endpoints_template.j2", "--output", str(out)], cwd=SRC, check=True)
    return out.read_text()


@pytest.fixture(scope="module")
def embedded_json(endpoints_hpp: str) -> str:
    """The text of the firmware's embedded_json[] (C string literals, one per line)."""
    body = endpoints_hpp[endpoints_hpp.index("embedded_json[] = "):]
    body = body[body.index('"'):body.index(";\n")]
    return "".join(line[1:-1].replace('\\"', '"') for line in body.splitlines())


@pytest.fixture(scope="module")
def generated_kinds(endpoints_hpp: str) -> dict[int, str]:
    body = endpoints_hpp[endpoints_hpp.index("EndpointKind endpoint_kind(int idx)"):]
    body = body[:body.index("default:")]
    kinds = {int(i): k for i, k in re.findall(r"case (\d+): return EndpointKind::(k\w+);", body)}
    assert len(kinds) == body.count("case "), "every case of endpoint_kind() parsed"
    return kinds


def entries(tree: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for e in tree:
        yield e
        for key in ("members", "inputs", "outputs"):
            yield from entries(e.get(key, []))


def expected_kind(e: dict[str, Any]) -> str:
    if e["type"] == "function":
        return "kFunction"
    return {"rw": "kReadWrite", "r": "kReadOnly"}[e["access"]]


def test_endpoint_kind_matches_the_json(embedded_json: str, generated_kinds: dict[int, str]) -> None:
    expected = {e["id"]: expected_kind(e) for e in entries(json.loads(embedded_json))
                if "id" in e and e["type"] != "json"}
    assert 0 not in generated_kinds  # endpoint 0 (the JSON itself) falls to the default, kNone
    assert generated_kinds == expected


def test_capture_finds_every_property_type(embedded_json: str) -> None:
    properties = [e for e in entries(json.loads(embedded_json))
                  if "id" in e and e["type"] not in ("function", "object", "json")]
    assert len(properties) > 400
    for e in properties:
        # Capture::add_channel's search key, followed by the type name and its closing quote
        assert f'"id":{e["id"]},"type":"{e["type"]}"' in embedded_json, e["name"]
