/* HoloGuard HG-1 housekeeping MCU (STM32G474) -- board support interface.
 * Implemented by target/bsp_stm32g4.c (STM32Cube HAL) and sim/bsp_sim.c
 * (host model with fault injection for unit tests).
 */
#ifndef HG1_BSP_H
#define HG1_BSP_H
#include <stdbool.h>
#include <stdint.h>

#define HG1_N_PA 6

typedef enum {
    RAIL_VIN = 0,   /* 12-36 V input (after LT4363)          */
    RAIL_28V,       /* GaN drain (LT8390)                    */
    RAIL_5V,        /* RF 5 V (LT8640S)                      */
    RAIL_3V3,       /* RFIC / LO LDO input                   */
    RAIL_NEG5,      /* GaN gate bias (LT3462), negative      */
    RAIL_COUNT
} bsp_rail_t;

typedef enum {
    EN_NEG5 = 0,    /* LT3462 enable                         */
    EN_28V,         /* LT8390 enable                         */
    EN_DRAIN_SW,    /* PA drain high-side switch (soft-start)*/
    EN_RF_5V,
    EN_TX_MUTE_N,   /* active-low hardware TX mute to ADAR1000 TR/PA_ON */
    EN_VERSAL,      /* DSP board power-good / enable         */
    EN_HEATER,      /* cold-start radome/board heater        */
    EN_COUNT
} bsp_enable_t;

typedef enum {
    TS_PA0 = 0,     /* TS_PA0..TS_PA5: NTC on each PA thermal pedestal */
    TS_RFIC = HG1_N_PA,
    TS_VERSAL,      /* via PMBus/SYSMON over I2C             */
    TS_HOUSING,
    TS_COUNT
} bsp_temp_t;

/* --- time ---------------------------------------------------------------- */
uint32_t bsp_millis(void);
void bsp_watchdog_kick(void);

/* --- analog monitors ------------------------------------------------------- */
int32_t bsp_rail_mv(bsp_rail_t r);          /* signed, NEG5 returns negative mV */
int32_t bsp_pa_idrain_ma(int pa);           /* drain-current sense per PA        */
int32_t bsp_temp_c10(bsp_temp_t s);         /* 0.1 degC                           */

/* --- controls -------------------------------------------------------------- */
void bsp_enable(bsp_enable_t e, bool on);
bool bsp_enabled(bsp_enable_t e);
/* GaN gate voltage via ADAR1000 PA_BIAS DAC (SPI), mV (negative) */
void bsp_pa_gate_mv(int pa, int32_t mv);
int32_t bsp_pa_gate_get_mv(int pa);
/* TX attenuation in ADAR1000 (0.1 dB units, >= 0) for thermal back-off */
void bsp_tx_atten_db10(int32_t db10);

/* --- status inputs --------------------------------------------------------- */
bool bsp_pll_locked(void);                  /* ADF4159 MUXOUT lock detect (both)  */
bool bsp_neg_rail_pgood(void);              /* hardware comparator, also gates drain switch */

/* --- link to Versal (UART 921600 8N1, DMA) --------------------------------- */
int bsp_link_write(const uint8_t* buf, int n);
int bsp_link_read(uint8_t* buf, int max);

#endif
