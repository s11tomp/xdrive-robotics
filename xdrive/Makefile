# Build the firmware from anywhere: `make -C xdrive` (or `cd xdrive && make`).
# Targets: all (default), asm, size, clean, reference (regenerates docs/reference.md). Variable: TOOLCHAIN.
HERE := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

.PHONY: all asm size clean venv reference
all asm size clean: venv
	$(MAKE) -C $(HERE)../Firmware -f ../xdrive/firmware.mk $@

reference: venv
	$(HERE).venv/bin/python $(HERE)tools/gen_reference.py

# Python env for the code generators (jinja2, PyYAML, jsonschema), via uv.
venv: $(HERE).venv/.done
$(HERE).venv/.done: $(HERE)requirements.txt
	cd $(HERE) && uv venv -q --clear --python 3.11 .venv && uv pip install -q --python .venv/bin/python -r requirements.txt && touch .venv/.done
