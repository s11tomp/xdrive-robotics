/* The CAN bootloader: flash sectors 0-1, CCM RAM only (main RAM holds the application's
   reset-surviving variables and the handoff, which the bootloader must leave as they are). */
ENTRY(Reset_Handler)

MEMORY
{
  FLASH (rx)   : ORIGIN = 0x08000000, LENGTH = 32K
  CCMRAM (rw)  : ORIGIN = 0x10000000, LENGTH = 64K
}

_estack = ORIGIN(CCMRAM) + LENGTH(CCMRAM);

SECTIONS
{
  /* The vector table, then the marker the flash tools look for at 0x08000200. */
  .isr_vector :
  {
    KEEP(*(.isr_vector))
    . = 0x200;
    KEEP(*(.boot_marker))
  } >FLASH

  .text :
  {
    . = ALIGN(4);
    *(.text*)
    *(.rodata*)
    . = ALIGN(4);
  } >FLASH

  .data :
  {
    . = ALIGN(4);
    _sdata = .;
    *(.data*)
    . = ALIGN(4);
    _edata = .;
  } >CCMRAM AT>FLASH
  _sidata = LOADADDR(.data);
  ASSERT(SIZEOF(.data) == 0, "the bootloader has no initialized data: its .bin holds only .isr_vector and .text")

  .bss (NOLOAD) :
  {
    . = ALIGN(4);
    _sbss = .;
    *(.bss*)
    *(COMMON)
    . = ALIGN(4);
    _ebss = .;
  } >CCMRAM

  .noinit (NOLOAD) :
  {
    *(.noinit*)
  } >CCMRAM

  /DISCARD/ :
  {
    *(.ARM.exidx*)
    *(.init_array*)
    *(.fini_array*)
  }
}
