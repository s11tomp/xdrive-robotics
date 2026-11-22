#!/usr/bin/env python3
"""Writes tools/xdrive/props.py and tools/xdrive/enums.py from src/odrive-interface.yaml.

props.py is the typed tree of every object, property and function the firmware exposes
(`odrv.axis0.encoder.pos_estimate` is a `Prop[float]`); enums.py has one class per enum
(`enum.Enum`) and per error bitfield (`enum.IntFlag`).

Usage: `make generate` (runs this with the repo's .venv).
"""
import keyword
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import gen_reference as ref  # noqa: E402
from type_info import BitfieldInfo, ClassInfo, EnumInfo  # noqa: E402

PROPS = ROOT / "tools" / "xdrive" / "props.py"
ENUMS = ROOT / "tools" / "xdrive" / "enums.py"
HEADER = ("# Generated from src/odrive-interface.yaml by `make generate` (tools/gen_props.py); "
          "edit the interface file, not this file.\n")
OPAQUE = {"float32": "float", "bool": "bool", "endpoint_ref": "EndpointRef",
          **{t: "int" for t in ("uint8", "uint16", "uint32", "uint64", "int32", "int64")}}
NS_PREFIX = "com.odriverobotics."


def enum_class_name(qualified):
    """'Axis.AxisState' -> 'AxisState'; 'Axis.Error' -> 'AxisError'; 'Error' -> 'ODriveError'."""
    *parents, name = qualified.split(".")
    if name in ("Error", "Mode", "Protocol"):
        return (parents[-1] if parents else "ODrive") + name
    return name


def class_names(reg):
    """Maps each object class to a Python class name from its registry path: 'ODrive.Axis.Config' -> 'AxisConfig'."""
    names = {}

    def walk(ns, path):
        for name, t in ns.types.items():
            if isinstance(t, ClassInfo):
                parts = ".".join((*path, name)).removeprefix(NS_PREFIX).split(".")
                names[id(t)] = "".join(parts[1:] if parts[0] == "ODrive" else parts)
        for name, sub in ns.namespaces.items():
            walk(sub, (*path, name))

    walk(reg.global_namespace, ())
    if len(set(names.values())) != len(names):
        raise SystemExit("two object classes map to the same Python class name")
    return names


def tup(items):
    """Python source for a tuple of the given element sources."""
    items = list(items)
    return f"({items[0]},)" if len(items) == 1 else f"({', '.join(items)})"


def check_identifier(name):
    if not name.isidentifier() or keyword.iskeyword(name):
        raise SystemExit(f"{name!r} is not usable as a Python identifier")
    return name


def render_enums(reg):
    out = [HEADER, '"""Enums and error bit flags of the firmware\'s interface."""', "import enum"]
    for qualified, t in ref.enum_types(reg):
        flags = isinstance(t, BitfieldInfo)
        out += ["", "", f"class {enum_class_name(qualified)}(enum.{'IntFlag' if flags else 'Enum'}):"]
        for m in (t.flags if flags else t.enumerators):
            out.append(f"    {check_identifier(m.name)} = {f'0x{1 << m.bit:08X}' if flags else m.value}")
    return "\n".join(out) + "\n"


def render_props(reg):
    enum_names = {id(t): enum_class_name(q) for q, t in ref.enum_types(reg)}
    cls_names = class_names(reg)

    def kind(t):
        t = ref.resolve(t)
        if isinstance(t, (EnumInfo, BitfieldInfo)):
            return f"E.{enum_names[id(t)]}"
        if t.name not in OPAQUE:
            raise SystemExit(f"no Python type for interface type {t.name}")
        return OPAQUE[t.name]

    out = [HEADER, '"""Typed names for every object, property and function of the firmware\'s interface.',
           "",
           "`odrv` is the board's root object: `board.get(odrv.axis0.encoder.pos_estimate)` returns a float.",
           '"""',
           "from __future__ import annotations", "",
           "from xdrive import enums as E",
           "from xdrive.model import Arg, Call, EndpointRef, Func, Prop, RwProp",
           "", "__all__ = [\"odrv\"]"]
    done = set()
    for _, cls in ref.objects(reg):
        if id(cls) in done:
            continue
        done.add(id(cls))
        name = cls_names[id(cls)]
        for f in ref.functions(cls):
            ins = [(check_identifier(a.name), kind(a.type)) for a in f.input_args]
            outs = [(a.name, kind(a.type)) for a in f.output_args]
            ret = "None" if not outs else outs[0][1] if len(outs) == 1 else f"tuple[{', '.join(k for _, k in outs)}]"
            in_args = tup(f"Arg({n!r}, {k})" for n, k in ins)
            out_args = tup(f"Arg({n!r}, {k})" for n, k in outs)
            out += ["", "", f"class {name}_{f.name}(Func[{ret}]):",
                    "    def __init__(self, path: str) -> None:",
                    f"        super().__init__(path, {in_args}, {out_args})",
                    "",
                    f"    def __call__(self{''.join(f', {n}: {k}' for n, k in ins)}) -> Call[{ret}]:",
                    f"        return Call(self, {tup(n for n, _ in ins)})"]
        out += ["", "", f"class {name}:", "    def __init__(self, p: str) -> None:"]
        body = []
        for a in ref.attributes(cls):
            t = ref.resolve(a.type)
            attr = check_identifier(a.name)
            if isinstance(t, ClassInfo):
                body.append(f'        self.{attr} = {cls_names[id(t)]}(p + "{a.name}.")')
            else:
                prop = "Prop" if a.readonly else "RwProp"
                body.append(f'        self.{attr}: {prop}[{kind(t)}] = {prop}(p + "{a.name}", {kind(t)})')
        for f in ref.functions(cls):
            body.append(f'        self.{check_identifier(f.name)} = {name}_{f.name}(p + "{f.name}")')
        out += body or ["        pass"]
    out += ["", "", f'odrv = {cls_names[id(reg.get_class(ref.ROOT_CLASS))]}("")']
    return "\n".join(out) + "\n"


def main():
    reg = ref.load(ref.INTERFACE)
    ENUMS.write_text(render_enums(reg))
    PROPS.write_text(render_props(reg))
    print(f"wrote {ENUMS.relative_to(ROOT)}, {PROPS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
