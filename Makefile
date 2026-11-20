# Build the firmware and run the checks, from the repo root (or `make -C <repo>` from anywhere).
#   all (default)  firmware -> build/firmware.{elf,hex,bin,map}
#   asm, size      disassembly (build/firmware.asm), section sizes
#   test           the firmware's unit tests (src/tests, on the host) and the host tools' tests (tools/tests)
#   generate       regenerates docs/reference.md, docs/cansimple.dbc and tools/enums_v056.py from
#                  src/odrive-interface.yaml; CI fails when the committed files differ from its output
#   clean
# Variables: TOOLCHAIN (Arm GCC's bin/ directory, with a trailing slash), HOST_CXX (default c++).
ROOT     := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
PYTHON   := $(ROOT).venv/bin/python
HOST_CXX ?= c++

.PHONY: all asm size clean test generate venv
all asm size clean: venv
	$(MAKE) -C $(ROOT)src PYTHON=$(PYTHON) $@

test: venv
	@mkdir -p $(ROOT)build/tests
	cd $(ROOT)src && $(HOST_CXX) -std=c++17 -O2 -I. -IMotorControl -Ifibre-cpp/include -IDrivers/DRV8301 -Itests/doctest \
		tests/*.cpp -o ../build/tests/unit_tests
	$(ROOT)build/tests/unit_tests
	cd $(ROOT) && $(PYTHON) -m pytest -q tools/tests

generate: venv
	cd $(ROOT) && $(PYTHON) tools/gen_reference.py
	cd $(ROOT) && $(PYTHON) tools/gen_dbc.py
	cd $(ROOT)src && $(PYTHON) -B ../tools/codegen/interface_generator.py --definitions odrive-interface.yaml \
		--template ../tools/codegen/enums_template.j2 --output ../tools/enums_v056.py

# One Python env for the code generators and the host tools, via uv.
venv: $(ROOT).venv/.done
$(ROOT).venv/.done: $(ROOT)requirements.txt
	cd $(ROOT) && uv venv -q --clear --python 3.11 .venv && uv pip install -q --python .venv/bin/python -r requirements.txt && touch .venv/.done
