#pragma once
// What the application leaves the CAN bootloader when it resets into it (enter_can_bootloader()):
// a request to stay, plus the bus settings the bootloader can't read from the config.
//
// It sits at a fixed address near the top of main RAM, inside the application's main (interrupt)
// stack. The application writes it with interrupts disabled immediately before its reset, so no
// stack use overwrites it, and the bootloader uses only CCM RAM, so the handoff survives until the
// bootloader reads and clears it. `check` guards against RAM contents that match `magic` by chance.
#include <stdint.h>

#define BOOT_HANDOFF_ADDR 0x2001FF00u
#define BOOT_HANDOFF_MAGIC 0x424F4F54u  /* "BOOT" */

struct BootHandoff {
    uint32_t magic;
    uint32_t node_id;    /* CANSimple node ID, 0..63 */
    uint32_t baud_rate;  /* the bus bit rate the application runs at */
    uint32_t check;      /* ~(magic ^ node_id ^ baud_rate) */
};

static inline uint32_t boot_handoff_check(const struct BootHandoff* h) {
    return ~(h->magic ^ h->node_id ^ h->baud_rate);
}
