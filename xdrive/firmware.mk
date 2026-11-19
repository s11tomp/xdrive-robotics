# Build the XDRIVE Mini firmware without tup (tup needs FUSE, which macOS lacks).
#
# Run through xdrive/Makefile, which calls this with cwd = Firmware/ (the compile commands use
# paths relative to Firmware/, exactly like tup did).
#
# Flags, defines, include order and link order replicate Makerbase's tup build of
# fw-v0.5.1-20250326, taken from the .tup/db in their source archive. With their compiler
# (GNU Arm Embedded 7-2018-q2-update), MAKERBASE_VERSION=1 and LIB_OVERRIDE, the output is
# byte-identical to xdrive/reference/makerbase-20250326/ODriveFirmware.bin: `make verify-makerbase`.

TOOLCHAIN ?= $(HOME)/.local/arm/gcc-arm-none-eabi-7-2018-q2-update/bin/
PREFIX    := $(TOOLCHAIN)arm-none-eabi-
CC        := $(PREFIX)gcc
CXX       := $(PREFIX)g++
OBJCOPY   := $(PREFIX)objcopy
OBJDUMP   := $(PREFIX)objdump
SIZE      := $(PREFIX)size
PYTHON    ?= ../xdrive/.venv/bin/python

# 1 = write autogen/version.c as Makerbase's build did (fw 0.0.0, unreleased); needed for a
# byte-identical build. 0 = tools/odrive/version.py from `git describe` (e.g. 0.5.1, unreleased).
MAKERBASE_VERSION ?= 0

# Optional: target-library dirs searched before the toolchain's own. Makerbase linked against the
# *Windows* release's libc/libstdc++/libgcc archives, whose member order differs from the Mac
# release's, so library code lands in a different order. For a byte-identical build point this at
# the Windows release's libraries (see README): LIB_OVERRIDE=<dir with arm-none-eabi/ and lib/gcc/>.
LIB_OVERRIDE ?=
LIBPATH := $(if $(LIB_OVERRIDE),-L$(LIB_OVERRIDE)/arm-none-eabi/lib/thumb/v7e-m/fpv4-sp/hard -L$(LIB_OVERRIDE)/lib/gcc/arm-none-eabi/7.3.1/thumb/v7e-m/fpv4-sp/hard)

BUILD := build
OBJ   := $(BUILD)/obj
ELF   := $(BUILD)/ODriveFirmware.elf
REF   := ../xdrive/reference/makerbase-20250326/ODriveFirmware.bin

# --- flags (order as in the tup commands) -------------------------------------------------------
DEFS := -DHW_VERSION_MAJOR=3 -DHW_VERSION_MINOR=6 -DHW_VERSION_VOLTAGE=56 \
        -DUSB_PROTOCOL_NATIVE -DUART_PROTOCOL_ASCII \
        '-D__weak=__attribute__((weak))' '-D__packed=__attribute__((__packed__))' \
        -DUSE_HAL_DRIVER -DSTM32F405xx
ARCH := -mthumb -mcpu=cortex-m4 -mfpu=fpv4-sp-d16 -mfloat-abi=hard
WARN := -Wall -Wdouble-promotion -Wfloat-conversion
OPT  := -fdata-sections -ffunction-sections -O2 -ffast-math -fno-finite-math-only
COMMON := $(DEFS) $(ARCH) $(WARN) $(OPT)

BOARD_INC := -IBoard/v3/Middlewares/Third_Party/FreeRTOS/Source/portable/GCC/ARM_CM4F \
             -IBoard/v3/Middlewares/Third_Party/FreeRTOS/Source/include \
             -IBoard/v3/Middlewares/Third_Party/FreeRTOS/Source/CMSIS_RTOS \
             -IBoard/v3/Middlewares/ST/STM32_USB_Device_Library/Core/Inc \
             -IBoard/v3/Middlewares/ST/STM32_USB_Device_Library/Class/CDC/Inc \
             -IBoard/v3/Drivers/STM32F4xx_HAL_Driver/Inc \
             -IBoard/v3/Drivers/STM32F4xx_HAL_Driver/Inc/Legacy \
             -IBoard/v3/Drivers/CMSIS/Device/ST/STM32F4xx/Include \
             -IBoard/v3/Drivers/CMSIS/Include \
             -IBoard/v3/Inc -I. -IDrivers/DRV8301
ODRIVE_INC := -IDrivers/DRV8301 -IMotorControl -Ifibre/cpp/include -I. -Idoctest $(BOARD_INC)

LDFLAGS := -TBoard/v3/STM32F405RGTx_FLASH.ld -LBoard/v3/Drivers/CMSIS/Lib \
           -lc -lm -lnosys -larm_cortexM4lf_math $(ARCH) \
           -specs=nosys.specs -specs=nano.specs -u _printf_float -u _scanf_float \
           -Wl,--cref -Wl,--gc-sections -Wl,--undefined=uxTopUsedPriority \
           -O2 -ffast-math -fno-finite-math-only -Wl,-Map=$(BUILD)/ODriveFirmware.map

# Dependency files only; -MMD/-MP don't change the generated code.
DEPFLAGS = -MMD -MP

# --- sources --------------------------------------------------------------------------------------
include ../xdrive/sources.mk

obj = $(patsubst %,$(OBJ)/%.o,$(1))
BOARD_C_OBJS  := $(call obj,$(BOARD_C_SRCS))
ODRIVE_C_OBJS := $(call obj,$(ODRIVE_C_SRCS))
CXX_OBJS      := $(call obj,$(CXX_SRCS))
ASM_OBJS      := $(call obj,$(ASM_SRCS))
LINK_OBJS     := $(call obj,$(LINK_SRCS))

AUTOGEN_HDRS := autogen/interfaces.hpp autogen/function_stubs.hpp autogen/endpoints.hpp autogen/type_info.hpp
GEN_DEPS     := odrive-interface.yaml interface_generator_stub.py fibre/tools/interface_generator.py

# --- targets --------------------------------------------------------------------------------------
.PHONY: all clean size asm verify-makerbase FORCE
all: $(BUILD)/ODriveFirmware.hex $(BUILD)/ODriveFirmware.bin size

$(ELF): $(LINK_OBJS) Board/v3/STM32F405RGTx_FLASH.ld
	$(CXX) $(LINK_OBJS) $(LIBPATH) $(LDFLAGS) -o $@

$(BUILD)/ODriveFirmware.hex: $(ELF)
	$(OBJCOPY) -O ihex $< $@

$(BUILD)/ODriveFirmware.bin: $(ELF)
	$(OBJCOPY) -O binary -S $< $@

size: $(ELF)
	@$(SIZE) $<

asm: $(ELF)
	$(OBJDUMP) $< -dSC > $(BUILD)/ODriveFirmware.asm

# Compile rules (-c <src> first, then flags, as tup did).
$(BOARD_C_OBJS): $(OBJ)/%.o: %
	@mkdir -p $(dir $@)
	$(CC) -std=c99 -c $< $(COMMON) $(BOARD_INC) $(DEPFLAGS) -o $@

$(ODRIVE_C_OBJS): $(OBJ)/%.o: % | $(AUTOGEN_HDRS)
	@mkdir -p $(dir $@)
	$(CC) -std=c99 -c $< $(COMMON) $(ODRIVE_INC) $(DEPFLAGS) -o $@

$(CXX_OBJS): $(OBJ)/%.o: % | $(AUTOGEN_HDRS)
	@mkdir -p $(dir $@)
	$(CXX) -std=c++17 -Wno-register -c $< $(COMMON) $(ODRIVE_INC) $(DEPFLAGS) -o $@

$(ASM_OBJS): $(OBJ)/%.o: %
	@mkdir -p $(dir $@)
	$(CC) -x assembler-with-cpp -c $< $(COMMON) $(BOARD_INC) -o $@

# Code generation (fibre interface headers), as in Tupfile.lua.
autogen/interfaces.hpp: $(GEN_DEPS) fibre/cpp/interfaces_template.j2
	@mkdir -p autogen
	$(PYTHON) -B interface_generator_stub.py --definitions odrive-interface.yaml --template fibre/cpp/interfaces_template.j2 --output $@
autogen/function_stubs.hpp: $(GEN_DEPS) fibre/cpp/function_stubs_template.j2
	@mkdir -p autogen
	$(PYTHON) -B interface_generator_stub.py --definitions odrive-interface.yaml --template fibre/cpp/function_stubs_template.j2 --output $@
autogen/endpoints.hpp: $(GEN_DEPS) fibre/cpp/endpoints_template.j2
	@mkdir -p autogen
	$(PYTHON) -B interface_generator_stub.py --definitions odrive-interface.yaml --generate-endpoints ODrive --template fibre/cpp/endpoints_template.j2 --output $@
autogen/type_info.hpp: $(GEN_DEPS) fibre/cpp/type_info_template.j2
	@mkdir -p autogen
	$(PYTHON) -B interface_generator_stub.py --definitions odrive-interface.yaml --template fibre/cpp/type_info_template.j2 --output $@

# version.c is regenerated every build but only rewritten when its content changes.
autogen/version.c: FORCE
	@mkdir -p autogen
ifeq ($(MAKERBASE_VERSION),1)
	@printf 'const unsigned char fw_version_major_ = 0;\nconst unsigned char fw_version_minor_ = 0;\nconst unsigned char fw_version_revision_ = 0;\nconst unsigned char fw_version_unreleased_ = 1;\n' > $@.tmp
else
	@$(PYTHON) -B ../tools/odrive/version.py --output $@.tmp
endif
	@cmp -s $@.tmp $@ && rm $@.tmp || mv $@.tmp $@

verify-makerbase: $(BUILD)/ODriveFirmware.bin
	@cmp $(BUILD)/ODriveFirmware.bin $(REF) && echo "IDENTICAL to Makerbase's 20250326 build (= the test-stand board's firmware)"

clean:
	rm -rf $(BUILD) autogen

-include $(shell find $(OBJ) -name '*.d' 2>/dev/null)
