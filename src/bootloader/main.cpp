// The CAN bootloader for the XDRIVE Mini, in flash sectors 0-1 (0x08000000, 32 KB). It updates the
// application (sectors 2-9) over CAN1 with the protocol in boot_protocol.hpp and starts it when its
// image header and CRC check out. Design: docs/bootloader.md.
//
// At every reset:
//   - a start request left by this bootloader (jump_request): start the application at once, before
//     touching clocks or peripherals, so it begins from the state a reset leaves;
//   - a request from the application (the handoff in handoff.h), or no valid image: stay and serve
//     the bus;
//   - a valid image after a power-up: listen STAY_WINDOW_MS for a DISCOVER, then start it;
//   - a valid image after any other reset: start it.
// Starting the application means setting jump_request and resetting.
//
// The gate driver stays disabled throughout (EN_GATE, PB12, low; the brake half-bridge's inputs have
// pull-downs), so the motor stays limp. The bootloader uses only CCM RAM: the application's reset-
// surviving variables (its DFU cookie) and the handoff are in main RAM and stay as they are.
#include <stddef.h>
#include <stdint.h>

#include "stm32f4xx.h"

#include "bootloader/boot_protocol.hpp"
#include "bootloader/handoff.h"

using namespace boot_protocol;

extern "C" {
extern uint32_t _sidata, _sdata, _edata, _sbss, _ebss, _estack;
void Reset_Handler(void);
void Fault_Handler(void);
int main(void);

// Freestanding: the compiler may call these for struct copies and clears.
void* memcpy(void* dst, const void* src, size_t n) {
    uint8_t* d = static_cast<uint8_t*>(dst);
    const uint8_t* s = static_cast<const uint8_t*>(src);
    while (n--) {
        *d++ = *s++;
    }
    return dst;
}

void* memset(void* dst, int c, size_t n) {
    uint8_t* d = static_cast<uint8_t*>(dst);
    while (n--) {
        *d++ = uint8_t(c);
    }
    return dst;
}

int memcmp(const void* a, const void* b, size_t n) {
    const uint8_t* x = static_cast<const uint8_t*>(a);
    const uint8_t* y = static_cast<const uint8_t*>(b);
    for (; n; --n, ++x, ++y) {
        if (*x != *y) {
            return *x < *y ? -1 : 1;
        }
    }
    return 0;
}
}

namespace {

constexpr uint32_t JUMP_MAGIC = 0x4A554D50;  // "JUMP"
constexpr uint32_t DEFAULT_BAUD = 1000000;   // the default CAN bitrate; the firmware's handoff overrides it
constexpr uint32_t STAY_WINDOW_MS = 100;
constexpr uint32_t CPU_HZ = 168000000;
constexpr uint32_t CAN_CLOCK = 42000000;     // APB1
constexpr uint32_t CAN_TQ = 21;              // 1 + 16 + 4 time quanta per bit, as the application uses

__attribute__((section(".noinit"))) volatile uint32_t jump_request;

[[noreturn]] void start_app() {
    const uint32_t* vectors = reinterpret_cast<const uint32_t*>(APP_START);
    SCB->VTOR = APP_START;
    __set_MSP(vectors[0]);
    reinterpret_cast<void (*)(void)>(vectors[1])();
    for (;;) {
    }
}

[[noreturn]] void request_app_start() {
    jump_request = JUMP_MAGIC;
    NVIC_SystemReset();
    for (;;) {
    }
}

uint32_t elapsed_ms(uint32_t start_cycles) {
    return (DWT->CYCCNT - start_cycles) / (CPU_HZ / 1000);
}

void gate_driver_off() {
    RCC->AHB1ENR |= RCC_AHB1ENR_GPIOBEN;
    (void)RCC->AHB1ENR;
    GPIOB->BSRR = GPIO_BSRR_BR12;
    GPIOB->MODER = (GPIOB->MODER & ~(3u << 24)) | (1u << 24);  // PB12 output, low
}

// 8 MHz HSE -> PLL -> 168 MHz; APB1 42 MHz (CAN), APB2 84 MHz: the application's clock tree.
void clock_init() {
    RCC->CR |= RCC_CR_HSEON;
    while (!(RCC->CR & RCC_CR_HSERDY)) {
    }
    FLASH->ACR = FLASH_ACR_LATENCY_5WS | FLASH_ACR_PRFTEN | FLASH_ACR_ICEN | FLASH_ACR_DCEN;
    RCC->CFGR = RCC_CFGR_HPRE_DIV1 | RCC_CFGR_PPRE1_DIV4 | RCC_CFGR_PPRE2_DIV2;
    RCC->PLLCFGR = (4u << RCC_PLLCFGR_PLLM_Pos) | (168u << RCC_PLLCFGR_PLLN_Pos) | RCC_PLLCFGR_PLLSRC_HSE
                   | (7u << RCC_PLLCFGR_PLLQ_Pos);  // PLLP = 2
    RCC->CR |= RCC_CR_PLLON;
    while (!(RCC->CR & RCC_CR_PLLRDY)) {
    }
    RCC->CFGR = (RCC->CFGR & ~RCC_CFGR_SW) | RCC_CFGR_SW_PLL;
    while ((RCC->CFGR & RCC_CFGR_SWS) != RCC_CFGR_SWS_PLL) {
    }
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

uint64_t serial_number() {  // the application's (and the DFU bootloader's) USB serial number
    uint32_t uid0 = *reinterpret_cast<const uint32_t*>(UID_BASE);
    uint32_t uid1 = *reinterpret_cast<const uint32_t*>(UID_BASE + 4);
    uint32_t uid2 = *reinterpret_cast<const uint32_t*>(UID_BASE + 8);
    return (uint64_t(uid0 + uid2) << 16) | (uid1 >> 16);
}

struct Flash {
    static constexpr uint32_t ERRORS = FLASH_SR_SOP | FLASH_SR_WRPERR | FLASH_SR_PGAERR | FLASH_SR_PGPERR | FLASH_SR_PGSERR;

    static void unlock() {
        if (FLASH->CR & FLASH_CR_LOCK) {
            FLASH->KEYR = 0x45670123;
            FLASH->KEYR = 0xCDEF89AB;
        }
        FLASH->SR = ERRORS;  // write 1 to clear
    }

    static bool done() {
        while (FLASH->SR & FLASH_SR_BSY) {
        }
        bool ok = !(FLASH->SR & ERRORS);
        FLASH->SR = ERRORS;
        return ok;
    }

    static void finish() {
        FLASH->CR = 0;
        FLASH->CR = FLASH_CR_LOCK;
        // Reads after an erase or program must not come from the caches.
        FLASH->ACR &= ~(FLASH_ACR_ICEN | FLASH_ACR_DCEN);
        FLASH->ACR |= FLASH_ACR_ICRST | FLASH_ACR_DCRST;
        FLASH->ACR &= ~(FLASH_ACR_ICRST | FLASH_ACR_DCRST);
        FLASH->ACR |= FLASH_ACR_ICEN | FLASH_ACR_DCEN;
    }

    bool erase(uint8_t sector) {
        if (sector < APP_SECTORS[0].number || sector > APP_SECTORS[sizeof(APP_SECTORS) / sizeof(Sector) - 1].number) {
            return false;
        }
        unlock();
        FLASH->CR = FLASH_CR_PSIZE_1 | FLASH_CR_SER | (uint32_t(sector) << FLASH_CR_SNB_Pos);
        FLASH->CR |= FLASH_CR_STRT;
        bool ok = done();
        finish();
        return ok;
    }

    bool program(uint32_t addr, const uint8_t* data, size_t len) {
        if (addr < APP_START || addr % 4 || len % 4 || len > APP_END - addr) {
            return false;
        }
        unlock();
        FLASH->CR = FLASH_CR_PSIZE_1 | FLASH_CR_PG;
        bool ok = true;
        for (size_t i = 0; i < len && ok; i += 4) {
            uint32_t word;
            memcpy(&word, data + i, 4);
            *reinterpret_cast<volatile uint32_t*>(addr + i) = word;
            ok = done();
        }
        finish();
        return ok;
    }

    const uint8_t* read(uint32_t addr) { return reinterpret_cast<const uint8_t*>(addr); }
};

// CAN1 on PB8 (RX) and PB9 (TX), alternate function 9; every extended frame to FIFO 0.
void can_init(uint32_t baud) {
    RCC->APB1ENR |= RCC_APB1ENR_CAN1EN;
    (void)RCC->APB1ENR;
    GPIOB->AFR[1] = (GPIOB->AFR[1] & ~0xFFu) | (9u << 0) | (9u << 4);
    GPIOB->OSPEEDR |= 0xFu << 16;
    GPIOB->MODER = (GPIOB->MODER & ~(0xFu << 16)) | (0xAu << 16);
    CAN1->MCR &= ~CAN_MCR_SLEEP;
    CAN1->MCR |= CAN_MCR_INRQ;
    while (!(CAN1->MSR & CAN_MSR_INAK)) {
    }
    CAN1->MCR |= CAN_MCR_ABOM | CAN_MCR_TXFP;
    uint32_t prescaler = CAN_CLOCK / (baud * CAN_TQ);
    CAN1->BTR = (3u << CAN_BTR_SJW_Pos) | (3u << CAN_BTR_TS2_Pos) | (15u << CAN_BTR_TS1_Pos) | (prescaler - 1);
    CAN1->FMR |= CAN_FMR_FINIT;
    CAN1->FA1R &= ~1u;
    CAN1->FS1R |= 1u;    // 32-bit
    CAN1->FM1R &= ~1u;   // mask mode
    CAN1->FFA1R &= ~1u;  // FIFO 0
    CAN1->sFilterRegister[0].FR1 = CAN_RI0R_IDE;  // ID: extended
    CAN1->sFilterRegister[0].FR2 = CAN_RI0R_IDE;  // mask: only the IDE bit
    CAN1->FA1R |= 1u;
    CAN1->FMR &= ~CAN_FMR_FINIT;
    CAN1->MCR &= ~CAN_MCR_INRQ;
    while (CAN1->MSR & CAN_MSR_INAK) {  // leaves once it sees 11 recessive bits
    }
}

bool can_receive(Frame& f) {
    if (CAN1->RF0R & CAN_RF0R_FOVR0) {
        CAN1->RF0R = CAN_RF0R_FOVR0;  // an overrun loses DATA frames; the block's length check catches it
    }
    if (!(CAN1->RF0R & CAN_RF0R_FMP0)) {
        return false;
    }
    CAN_FIFOMailBox_TypeDef& mb = CAN1->sFIFOMailBox[0];
    uint32_t rir = mb.RIR;
    f.len = uint8_t(mb.RDTR & 0xF);
    if (f.len > 8) {
        f.len = 8;
    }
    uint32_t lo = mb.RDLR;
    uint32_t hi = mb.RDHR;
    CAN1->RF0R = CAN_RF0R_RFOM0;
    put_u32(f.data, lo);
    put_u32(f.data + 4, hi);
    f.id = rir >> 3;
    return (rir & CAN_RI0R_IDE) != 0;
}

// Waits up to 10 ms for a free mailbox; a frame nobody acknowledges is dropped after that.
void can_send(const Frame& f) {
    uint32_t start = DWT->CYCCNT;
    while (!(CAN1->TSR & CAN_TSR_TME)) {
        if (elapsed_ms(start) > 10) {
            return;
        }
    }
    uint32_t box = (CAN1->TSR & CAN_TSR_CODE) >> CAN_TSR_CODE_Pos;
    CAN_TxMailBox_TypeDef& mb = CAN1->sTxMailBox[box];
    mb.TDTR = f.len;
    mb.TDLR = get_u32(f.data);
    mb.TDHR = get_u32(f.data + 4);
    mb.TIR = (f.id << 3) | CAN_TI0R_IDE | CAN_TI0R_TXRQ;
}

void can_flush() {
    uint32_t start = DWT->CYCCNT;
    while ((CAN1->TSR & CAN_TSR_TME) != CAN_TSR_TME && elapsed_ms(start) < 10) {
    }
}

bool baud_ok(uint32_t baud) {
    return baud && CAN_CLOCK % (baud * CAN_TQ) == 0;
}

}  // namespace

// The bootloader's marker, at BOOT_START + HEADER_OFFSET: the flash tools check it before writing an
// application linked behind a bootloader.
__attribute__((section(".boot_marker"), used)) const uint32_t boot_marker[4] = {BOOTLOADER_MAGIC, PROTOCOL_VERSION, 0, 0};

__attribute__((section(".isr_vector"), used)) void (*const vectors[16])(void) = {
    reinterpret_cast<void (*)(void)>(&_estack), Reset_Handler,
    Fault_Handler, Fault_Handler, Fault_Handler, Fault_Handler, Fault_Handler,  // NMI to usage fault
    nullptr, nullptr, nullptr, nullptr,
    Fault_Handler, Fault_Handler, nullptr, Fault_Handler, Fault_Handler,         // SVC, debug, PendSV, SysTick
};

extern "C" void Fault_Handler(void) {
    for (;;) {  // the gate driver stays off; a reset or power cycle leaves
    }
}

extern "C" void Reset_Handler(void) {
    if (jump_request == JUMP_MAGIC) {
        jump_request = 0;
        start_app();
    }
    for (uint32_t *src = &_sidata, *dst = &_sdata; dst < &_edata;) {
        *dst++ = *src++;
    }
    for (uint32_t* dst = &_sbss; dst < &_ebss;) {
        *dst++ = 0;
    }
    main();
    for (;;) {
    }
}

int main(void) {
    gate_driver_off();
    bool power_up = (RCC->CSR & (RCC_CSR_PORRSTF | RCC_CSR_BORRSTF)) != 0;
    RCC->CSR |= RCC_CSR_RMVF;

    volatile BootHandoff* h = reinterpret_cast<volatile BootHandoff*>(BOOT_HANDOFF_ADDR);
    BootHandoff copy = {h->magic, h->node_id, h->baud_rate, h->check};
    bool requested = copy.magic == BOOT_HANDOFF_MAGIC && copy.check == boot_handoff_check(&copy) && copy.node_id < 64;
    h->magic = 0;
    uint8_t node = requested ? uint8_t(copy.node_id) : NODE_UNKNOWN;
    uint32_t baud = requested && baud_ok(copy.baud_rate) ? copy.baud_rate : DEFAULT_BAUD;

    clock_init();
    Flash flash;
    Session<Flash> session(flash, serial_number(), node, requested);
    bool valid = session.flags() & FLAG_IMAGE_VALID;
    if (valid && !requested && !power_up) {
        request_app_start();
    }

    can_init(baud);
    bool stay = requested || !valid;
    uint32_t window_start = DWT->CYCCNT;
    for (;;) {
        if (!stay && elapsed_ms(window_start) >= STAY_WINDOW_MS) {
            request_app_start();
        }
        Frame in;
        if (!can_receive(in)) {
            continue;
        }
        Frame out;
        Session<Flash>::Action action;
        if (session.handle(in, out, action)) {
            stay = true;
            can_send(out);
        }
        if (action == Session<Flash>::ACTION_START_APP) {
            can_flush();
            request_app_start();
        }
    }
}
