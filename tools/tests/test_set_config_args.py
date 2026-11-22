"""set_config.parse_args: a bare --save is allowed (it saves the RAM config); no arguments at all is not."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from set_config import parse_args  # noqa: E402


def test_nothing_to_do_is_rejected(capsys):
    with pytest.raises(SystemExit) as exc:
        parse_args([])
    assert exc.value.code == 2
    assert "nothing to do" in capsys.readouterr().err


def test_save_alone_is_accepted():
    args = parse_args(["--save"])
    assert args.save and not args.assignments and args.file is None


def test_assignments_and_file_are_accepted():
    assert parse_args(["a.b=1"]).assignments == ["a.b=1"]
    assert parse_args(["--file", "x.json"]).file == "x.json"


def test_malformed_assignment_is_rejected(capsys):
    with pytest.raises(SystemExit) as exc:
        parse_args(["axis0.config.watchdog_timeout"])
    assert exc.value.code == 2
    assert "expected path=value" in capsys.readouterr().err
