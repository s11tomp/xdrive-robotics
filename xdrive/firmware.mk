# Build the XDRIVE Mini firmware (ODrive v0.5.6 + Makerbase + ours) without tup (tup needs FUSE,
# which macOS lacks). Run through xdrive/Makefile, which calls this with cwd = Firmware/.
#
# Flags follow Firmware/Tupfile.lua for board v3.6-56V (see xdrive/sources.mk). The v0.5.1 build
# that reproduces Makerbase's binary byte for byte is at tag xdrive/v0.5.1.

TOOLCHAIN ?= $(HOME)/.local/arm/gcc-arm-none-eabi-10.3-2021.10/bin/
PREFIX    := $(TOOLCHAIN)arm-none-eabi-
CC        := $(PREFIX)gcc -std=c99
CXX       := $(PREFIX)g++ -std=c++17 -Wno-register
LINKER    := $(PREFIX)g++
OBJCOPY   := $(PREFIX)objcopy
OBJDUMP   := $(PREFIX)objdump
SIZE      := $(PREFIX)size
PYTHON    ?= ../xdrive/.venv/bin/python

BUILD := build
OBJ   := $(BUILD)/obj
ELF   := $(BUILD)/ODriveFirmware.elf

include ../xdrive/sources.mk

# Global CFLAGS from Tupfile.lua (non-debug build), then the package flags.
CFLAGS := '-D__weak=__attribute__((weak))' '-D__packed=__attribute__((__packed__))' -DUSE_HAL_DRIVER \
          -mthumb -mfloat-abi=hard -Wno-psabi -Wall -Wdouble-promotion -Wfloat-conversion \
          -fdata-sections -ffunction-sections -g -DFIBRE_ENABLE_SERVER -Wno-nonnull -O2 \
          $(PKG_FLAGS)
LDFLAGS := -flto -lc -lm -lnosys -mthumb -mfloat-abi=hard -specs=nosys.specs -u _printf_float -u _scanf_float \
           -Wl,--cref -Wl,--gc-sections -Wl,--undefined=uxTopUsedPriority $(PKG_LDFLAGS)
DEPFLAGS = -MMD -MP

OBJS     := $(patsubst %,$(OBJ)/%.o,$(SRCS))
C_OBJS   := $(patsubst %,$(OBJ)/%.o,$(filter %.c,$(SRCS)))
CXX_OBJS := $(patsubst %,$(OBJ)/%.o,$(filter %.cpp,$(SRCS)))
ASM_OBJS := $(patsubst %,$(OBJ)/%.o,$(filter %.s,$(SRCS)))

AUTOGEN_HDRS := autogen/interfaces.hpp autogen/function_stubs.hpp autogen/endpoints.hpp autogen/type_info.hpp
GEN_DEPS     := odrive-interface.yaml interface_generator_stub.py

.PHONY: all clean size asm FORCE
all: $(BUILD)/ODriveFirmware.hex $(BUILD)/ODriveFirmware.bin size

$(ELF): $(OBJS) Board/v3/STM32F405RGTx_FLASH.ld
	$(LINKER) $(OBJS) $(CFLAGS) $(LDFLAGS) -Wl,-Map=$(BUILD)/ODriveFirmware.map -o $@

$(BUILD)/ODriveFirmware.hex: $(ELF)
	$(OBJCOPY) -O ihex $< $@

$(BUILD)/ODriveFirmware.bin: $(ELF)
	$(OBJCOPY) -O binary -S $< $@

size: $(ELF)
	@$(SIZE) $<

asm: $(ELF)
	$(OBJDUMP) $< -dSC > $(BUILD)/ODriveFirmware.asm

$(C_OBJS): $(OBJ)/%.o: % | $(AUTOGEN_HDRS)
	@mkdir -p $(dir $@)
	$(CC) -c $< $(CFLAGS) $(DEPFLAGS) -o $@

$(CXX_OBJS): $(OBJ)/%.o: % | $(AUTOGEN_HDRS)
	@mkdir -p $(dir $@)
	$(CXX) -c $< $(CFLAGS) $(DEPFLAGS) -o $@

$(ASM_OBJS): $(OBJ)/%.o: %
	@mkdir -p $(dir $@)
	$(PREFIX)gcc -c $< $(CFLAGS) -o $@

# Code generation (fibre interface headers), as in Tupfile.lua. ODrive3 = the v3 board's root interface.
autogen/interfaces.hpp: $(GEN_DEPS) fibre-cpp/interfaces_template.j2
	@mkdir -p autogen
	$(PYTHON) -B interface_generator_stub.py --definitions odrive-interface.yaml --template fibre-cpp/interfaces_template.j2 --output $@
autogen/function_stubs.hpp: $(GEN_DEPS) fibre-cpp/function_stubs_template.j2
	@mkdir -p autogen
	$(PYTHON) -B interface_generator_stub.py --definitions odrive-interface.yaml --template fibre-cpp/function_stubs_template.j2 --output $@
autogen/endpoints.hpp: $(GEN_DEPS) fibre-cpp/endpoints_template.j2
	@mkdir -p autogen
	$(PYTHON) -B interface_generator_stub.py --definitions odrive-interface.yaml --generate-endpoints ODrive3 --template fibre-cpp/endpoints_template.j2 --output $@
autogen/type_info.hpp: $(GEN_DEPS) fibre-cpp/type_info_template.j2
	@mkdir -p autogen
	$(PYTHON) -B interface_generator_stub.py --definitions odrive-interface.yaml --template fibre-cpp/type_info_template.j2 --output $@

# version.c: from `git describe` via tools/odrive/version.py; only rewritten when it changes.
autogen/version.c: FORCE
	@mkdir -p autogen
	@$(PYTHON) -B ../tools/odrive/version.py --output $@.tmp
	@cmp -s $@.tmp $@ && rm $@.tmp || mv $@.tmp $@

clean:
	rm -rf $(BUILD) autogen

-include $(shell find $(OBJ) -name '*.d' 2>/dev/null)
