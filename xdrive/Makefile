# Build the firmware from anywhere: `make -C xdrive` (or `cd xdrive && make`).
# Targets: all (default), verify-makerbase, asm, size, clean. Variables: TOOLCHAIN, MAKERBASE_VERSION.
HERE := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

.PHONY: all verify-makerbase asm size clean venv
all verify-makerbase asm size clean: venv
	$(MAKE) -C $(HERE)../Firmware -f ../xdrive/firmware.mk $@

# Python env for the code generators (jinja2, PyYAML, jsonschema), via uv.
venv: $(HERE).venv/.done
$(HERE).venv/.done: $(HERE)requirements.txt
	cd $(HERE) && uv venv -q --clear --python 3.11 .venv && uv pip install -q --python .venv/bin/python -r requirements.txt && touch .venv/.done
