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
           -Wl,--cref -Wl,--gc-sections -Wl,--undefined=uxTopUsedPriority $(PKG_LDFLAGS) \
           -Wl,-z,max-page-size=0x4000  # else the ELF headers load at 0x08000000, over the bootloader
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
all: $(BUILD)/firmware.hex $(BUILD)/firmware.bin $(BUILD)/bootloader.hex $(BUILD)/bootloader.bin \
     $(BUILD)/firmware-with-bootloader.bin size

# The CAN bootloader (flash sectors 0-1): one freestanding source, no HAL, no libc, CCM RAM only.
BOOT_ELF    := $(BUILD)/bootloader.elf
BOOT_CFLAGS := -std=c++17 -mcpu=cortex-m4 -mthumb -mfloat-abi=soft -Os -g -Wall -Wextra -Werror -ffreestanding \
               -fno-exceptions -fno-rtti -fno-threadsafe-statics -fno-use-cxa-atexit -ffunction-sections -fdata-sections \
               -DSTM32F405xx -I. -IThirdParty/CMSIS/Include -IThirdParty/CMSIS/Device/ST/STM32F4xx/Include

$(BOOT_ELF): bootloader/main.cpp bootloader/boot_protocol.hpp bootloader/handoff.h bootloader/bootloader.ld
	@mkdir -p $(BUILD)
	$(PREFIX)g++ $(BOOT_CFLAGS) bootloader/main.cpp -nostdlib -Wl,--gc-sections -Tbootloader/bootloader.ld \
		-Wl,-Map=$(BUILD)/bootloader.map -lgcc -o $@
	@$(SIZE) $@

$(BUILD)/bootloader.hex: $(BOOT_ELF)
	$(OBJCOPY) -O ihex $< $@

$(BUILD)/bootloader.bin: $(BOOT_ELF)
	$(OBJCOPY) -O binary --gap-fill 0xFF -j .isr_vector -j .text $< $@

# Linked behind the CAN bootloader (0x08008000), then sealed: tools/seal_image.py writes the image
# length, CRC and version into its header and writes the .bin and .hex from the same bytes (objcopy's
# would differ in the padding between sections, which the CRC covers).
$(ELF): $(OBJS) Board/v3/STM32F405RGTx_FLASH.ld ../tools/seal_image.py Makefile
	$(LINKER) $(OBJS) $(CFLAGS) $(LDFLAGS) -Wl,-Map=$(BUILD)/firmware.map -o $@
	$(PYTHON) -B ../tools/seal_image.py $@ --version-c $(AUTOGEN)/version.c --bin $(BUILD)/firmware.bin \
		--hex $(BUILD)/firmware.hex

$(BUILD)/firmware.hex $(BUILD)/firmware.bin: $(ELF)
	@test -f $@

# Bootloader and firmware as one image from 0x08000000, for the one-time changeover over USB:
# usb_flash.py --bin build/firmware-with-bootloader.bin
$(BUILD)/firmware-with-bootloader.bin: $(BUILD)/bootloader.bin $(BUILD)/firmware.bin
	$(PYTHON) -B -c "import sys; b, a = (open(p, 'rb').read() for p in sys.argv[1:3]); assert len(b) <= 0x8000; \
		open(sys.argv[3], 'wb').write(b.ljust(0x8000, b'\xff') + a)" $^ $@

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
