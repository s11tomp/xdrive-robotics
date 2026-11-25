#!/usr/bin/env python3
"""Writes docs/reference.md from src/odrive-interface.yaml: every object, property, function,
enum and error bit the firmware exposes over USB, with the items this firmware adds to ODrive v0.5.6 marked.

The ODrive v0.5.6 interface comes from the tag upstream/fw-v0.5.6, so the repo needs that tag.

Usage: `make generate` (runs this with the repo's .venv).
"""
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "codegen"))
import interface_parser  # noqa: E402
import type_registry  # noqa: E402
from type_info import BitfieldInfo, ClassInfo, EnumInfo  # noqa: E402

INTERFACE = ROOT / "src" / "odrive-interface.yaml"
OUTPUT = ROOT / "docs" / "reference.md"
UPSTREAM_TAG = "upstream/fw-v0.5.6"
ROOT_CLASS = "com.odriverobotics.ODrive3"  # the device: ODrive plus the board config and axis0
TYPES_NS = "com.odriverobotics.ODrive"
ADDED = " (added)"


def load(path):
    reg = type_registry.TypeRegistry()
    interface_parser.Loader(reg).load_from_yaml_file(str(path))
    reg.resolve_all()
    return reg


def resolve(t):
    return t.resolve() if hasattr(t, "resolve") else t


def attributes(cls):
    """The class's attributes, after those of the classes it implements."""
    return [a for base in cls.implements for a in attributes(resolve(base))] + cls.attributes


def functions(cls):
    return [f for base in cls.implements for f in functions(resolve(base))] + cls.functions


def qualified_names(reg):
    """Maps each enum and bitfield type to its name below com.odriverobotics.ODrive, e.g. 'Axis.Error'."""
    names = {}

    def walk(ns, path):
        for name, t in ns.types.items():
            if isinstance(t, (EnumInfo, BitfieldInfo)):
                names[id(t)] = ".".join((*path, name))
        for name, sub in ns.namespaces.items():
            walk(sub, (*path, name))

    walk(reg.global_namespace.ns_from_path(tuple(TYPES_NS.split(".")), construct_if_missing=False), ())
    return names


def objects(reg):
    """(path, class) for every object reachable from the root, depth first, e.g. ('odrv0.axis0', Axis)."""
    out = []

    def walk(cls, path):
        out.append((path, cls))
        for a in attributes(cls):
            t = resolve(a.type)
            if isinstance(t, ClassInfo):
                walk(t, f"{path}.{a.name}")

    walk(reg.get_class(ROOT_CLASS), "odrv0")
    return out


def enum_types(reg):
    names = qualified_names(reg)
    seen = {}
    for _, cls in objects(reg):
        for a in attributes(cls):
            t = resolve(a.type)
            if isinstance(t, (EnumInfo, BitfieldInfo)):
                seen[id(t)] = (names[id(t)], t)
    return sorted(seen.values(), key=lambda nt: nt[0])


def known_items(reg):
    """Every property, function and enum value path, for comparing two interfaces."""
    items = set()
    for path, cls in objects(reg):
        items.update(f"{path}.{a.name}" for a in attributes(cls))
        items.update(f"{path}.{f.name}()" for f in functions(cls))
    for name, t in enum_types(reg):
        members = t.flags if isinstance(t, BitfieldInfo) else t.enumerators
        items.add(name)
        items.update(f"{name}.{m.name}" for m in members)
    return items


def upstream_items():
    text = subprocess.run(["git", "-C", str(ROOT), "show", f"{UPSTREAM_TAG}:Firmware/odrive-interface.yaml"],
                          check=True, capture_output=True, text=True).stdout
    with tempfile.NamedTemporaryFile("w", suffix=".yaml") as f:
        f.write(text)
        f.flush()
        return known_items(load(f.name))


def text(*parts):
    """One table cell from brief and doc strings: paragraphs joined with <br>, pipes escaped."""
    paras = []
    for part in parts:
        for para in re.split(r"\n\s*\n", part or ""):
            para = " ".join(para.split())
            if para:
                paras.append(para.replace("|", "\\|"))
    return "<br>".join(paras)


def slug(heading):
    """GitHub's anchor for a heading."""
    return re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")


def type_cell(t, names):
    if isinstance(t, (EnumInfo, BitfieldInfo)):
        name = names[id(t)]
        return f"[{name}](#{slug(name)})"
    return t.name


def render(reg, upstream):
    names = qualified_names(reg)
    out = [
        "# Property reference",
        "",
        "Every object, property, function, enum and error bit the firmware exposes over USB, as the host tools "
        "and the `xdrive` library see them (`odrv.axis0.controller.config.pos_gain`). Items marked *(added)* are not in ODrive "
        "v0.5.6. Access: `rw` can be written, `ro` is read-only. Settings under a `config` object persist after "
        "`save_configuration()`; everything else resets at boot.",
        "",
        "This file is generated from `src/odrive-interface.yaml` by `tools/gen_reference.py`; edit the interface "
        "file and run `make generate` instead of editing this file.",
        "",
        "## Objects",
        "",
    ]
    for path, cls in objects(reg):
        out += [f"### {path}", ""]
        props = [a for a in attributes(cls) if not isinstance(resolve(a.type), ClassInfo)]
        subs = [a for a in attributes(cls) if isinstance(resolve(a.type), ClassInfo)]
        if props:
            out += ["| Property | Type | Unit | Access | Description |", "|---|---|---|---|---|"]
            for a in props:
                mark = "" if f"{path}.{a.name}" in upstream else ADDED
                out.append(f"| `{a.name}`{mark} | {type_cell(resolve(a.type), names)} | {a.unit or ''} | "
                           f"{'ro' if a.readonly else 'rw'} | {text(a.brief, a.doc)} |")
            out.append("")
        if functions(cls):
            out += ["| Function | Description |", "|---|---|"]
            for f in functions(cls):
                args = ", ".join(f"{x.name}: {type_cell(resolve(x.type), names)}" for x in f.input_args)
                ret = ", ".join(type_cell(resolve(x.type), names) for x in f.output_args)
                mark = "" if f"{path}.{f.name}()" in upstream else ADDED
                out.append(f"| `{f.name}({args})`{' -> ' + ret if ret else ''}{mark} | {text(f.brief, f.doc)} |")
            out.append("")
        if subs:
            out += ["Objects: " + ", ".join(f"[{a.name}](#{slug(f'{path}.{a.name}')})" for a in subs), ""]

    out += ["## Enums and error bits", ""]
    for name, t in enum_types(reg):
        flags = isinstance(t, BitfieldInfo)
        mark = "" if name in upstream else ADDED
        out += [f"### {name}", "", f"{'Bit flags' if flags else 'Enum'}{mark}.", "",
                "| Name | Value | Description |", "|---|---|---|"]
        for m in (t.flags if flags else t.enumerators):
            value = f"0x{1 << m.bit:08X}" if flags else str(m.value)
            mark = "" if f"{name}.{m.name}" in upstream else ADDED
            out.append(f"| `{m.name}`{mark} | {value} | {text(m.brief, m.doc)} |")
        out.append("")
    return "\n".join(out)


def main():
    OUTPUT.write_text(render(load(INTERFACE), upstream_items()))
    print(f"wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
