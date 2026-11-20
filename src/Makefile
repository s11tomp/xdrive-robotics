# Builds the XDRIVE Mini firmware (ODrive v0.5.6 + Makerbase + this firmware's changes) with plain
# make. The top-level Makefile runs this with cwd = src/, so compiler paths (and __FILE__ strings)
# are relative to src/. Output goes to ../build/.
#
# Flags follow ODrive v0.5.6's Tupfile.lua for board v3.6-56V (see sources.mk). The v0.5.1 build
# that reproduces Makerbase's binary byte for byte is at tag xdrive/v0.5.1.

TOOLCHAIN ?= $(HOME)/.local/arm/gcc-arm-none-eabi-10.3-2021.10/bin/
PREFIX    := $(TOOLCHAIN)arm-none-eabi-
CC        := $(PREFIX)gcc -std=c99
CXX       := $(PREFIX)g++ -std=c++17 -Wno-register
LINKER    := $(PREFIX)g++
OBJCOPY   := $(PREFIX)objcopy
OBJDUMP   := $(PREFIX)objdump
SIZE      := $(PREFIX)size
PYTHON    ?= ../.venv/bin/python

BUILD   := ../build
OBJ     := $(BUILD)/obj
AUTOGEN := $(BUILD)/autogen
ELF     := $(BUILD)/firmware.elf

include sources.mk

# Global CFLAGS from Tupfile.lua (non-debug build), then the package flags. Sources include the
# generated headers as <autogen/...>, found through -I$(BUILD).
CFLAGS := '-D__weak=__attribute__((weak))' '-D__packed=__attribute__((__packed__))' -DUSE_HAL_DRIVER \
          -mthumb -mfloat-abi=hard -Wno-psabi -Wall -Wdouble-promotion -Wfloat-conversion \
          -fdata-sections -ffunction-sections -g -DFIBRE_ENABLE_SERVER -Wno-nonnull -O2 \
          $(PKG_FLAGS) -I$(BUILD)
LDFLAGS := -flto -lc -lm -lnosys -mthumb -mfloat-abi=hard -specs=nosys.specs -u _printf_float -u _scanf_float \
           -Wl,--cref -Wl,--gc-sections -Wl,--undefined=uxTopUsedPriority $(PKG_LDFLAGS)
DEPFLAGS = -MMD -MP

# version.c is generated, so it is compiled from $(AUTOGEN); it links last, as in Tupfile.lua.
VERSION_OBJ := $(OBJ)/autogen/version.c.o
OBJS     := $(patsubst %,$(OBJ)/%.o,$(SRCS)) $(VERSION_OBJ)
C_OBJS   := $(patsubst %,$(OBJ)/%.o,$(filter %.c,$(SRCS)))
CXX_OBJS := $(patsubst %,$(OBJ)/%.o,$(filter %.cpp,$(SRCS)))
ASM_OBJS := $(patsubst %,$(OBJ)/%.o,$(filter %.s,$(SRCS)))

AUTOGEN_HDRS := $(AUTOGEN)/interfaces.hpp $(AUTOGEN)/function_stubs.hpp $(AUTOGEN)/endpoints.hpp $(AUTOGEN)/type_info.hpp
GENERATOR    := ../tools/codegen/interface_generator.py
GEN_DEPS     := odrive-interface.yaml $(wildcard ../tools/codegen/*.py)

.PHONY: all clean size asm FORCE
all: $(BUILD)/firmware.hex $(BUILD)/firmware.bin size

$(ELF): $(OBJS) Board/v3/STM32F405RGTx_FLASH.ld
	$(LINKER) $(OBJS) $(CFLAGS) $(LDFLAGS) -Wl,-Map=$(BUILD)/firmware.map -o $@

$(BUILD)/firmware.hex: $(ELF)
	$(OBJCOPY) -O ihex $< $@

$(BUILD)/firmware.bin: $(ELF)
	$(OBJCOPY) -O binary -S $< $@

size: $(ELF)
	@$(SIZE) $<

asm: $(ELF)
	$(OBJDUMP) $< -dSC > $(BUILD)/firmware.asm

$(C_OBJS): $(OBJ)/%.o: % | $(AUTOGEN_HDRS)
	@mkdir -p $(dir $@)
	$(CC) -c $< $(CFLAGS) $(DEPFLAGS) -o $@

$(CXX_OBJS): $(OBJ)/%.o: % | $(AUTOGEN_HDRS)
	@mkdir -p $(dir $@)
	$(CXX) -c $< $(CFLAGS) $(DEPFLAGS) -o $@

$(ASM_OBJS): $(OBJ)/%.o: %
	@mkdir -p $(dir $@)
	$(PREFIX)gcc -c $< $(CFLAGS) -o $@

$(VERSION_OBJ): $(AUTOGEN)/version.c
	@mkdir -p $(dir $@)
	$(CC) -c $< $(CFLAGS) $(DEPFLAGS) -o $@

# Code generation (fibre interface headers), as in Tupfile.lua. ODrive3 = the v3 board's root interface.
$(AUTOGEN)/interfaces.hpp: $(GEN_DEPS) fibre-cpp/interfaces_template.j2
	@mkdir -p $(AUTOGEN)
	$(PYTHON) -B $(GENERATOR) --definitions odrive-interface.yaml --template fibre-cpp/interfaces_template.j2 --output $@
$(AUTOGEN)/function_stubs.hpp: $(GEN_DEPS) fibre-cpp/function_stubs_template.j2
	@mkdir -p $(AUTOGEN)
	$(PYTHON) -B $(GENERATOR) --definitions odrive-interface.yaml --template fibre-cpp/function_stubs_template.j2 --output $@
$(AUTOGEN)/endpoints.hpp: $(GEN_DEPS) fibre-cpp/endpoints_template.j2
	@mkdir -p $(AUTOGEN)
	$(PYTHON) -B $(GENERATOR) --definitions odrive-interface.yaml --generate-endpoints ODrive3 --template fibre-cpp/endpoints_template.j2 --output $@
$(AUTOGEN)/type_info.hpp: $(GEN_DEPS) fibre-cpp/type_info_template.j2
	@mkdir -p $(AUTOGEN)
	$(PYTHON) -B $(GENERATOR) --definitions odrive-interface.yaml --template fibre-cpp/type_info_template.j2 --output $@

# version.c: from `git describe` via tools/version.py; only rewritten when it changes.
$(AUTOGEN)/version.c: FORCE
	@mkdir -p $(AUTOGEN)
	@$(PYTHON) -B ../tools/version.py --output $@.tmp
	@cmp -s $@.tmp $@ && rm $@.tmp || mv $@.tmp $@

clean:
	rm -rf $(BUILD)

-include $(shell find $(OBJ) -name '*.d' 2>/dev/null)
