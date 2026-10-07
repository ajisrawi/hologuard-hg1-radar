/* HoloGuard HG-1 housekeeping MCU -- module interfaces. */
#ifndef HG1_MCU_H
#define HG1_MCU_H
#include <stdbool.h>
#include <stdint.h>

#include "bsp.h"
#include "hg1_protocol.h"

/* ---------------- GaN power sequencing (power_seq.c) ---------------------- */
typedef struct {
    int32_t vneg_min_mv;        /* -5 V rail must be below this (e.g. -4750)   */
    int32_t vg_pinchoff_mv;     /* gate parked here before drain (e.g. -4000)  */
    int32_t vg_start_mv;        /* trim start                                  */
    int32_t vg_max_mv;          /* never above (protect against runaway)       */
    int32_t v28_min_mv, v28_max_mv;
    int32_t idq_target_ma;      /* quiescent drain current per PA              */
    int32_t idq_tol_ma;
    int32_t id_max_ma;          /* over-current trip per PA                    */
    uint32_t neg_settle_ms, drain_ramp_ms, trim_timeout_ms;
    int32_t vg_step_mv;
} pwr_cfg_t;

typedef struct {
    uint8_t state;              /* enum hg1_pwr_state */
    uint32_t t_state;           /* ms when state entered */
    uint32_t faults;            /* latched FAULT_* */
    bool tx_request;            /* host asked for TX */
    bool tx_on;
    bool up_request;
    int32_t vg_mv[HG1_N_PA];
    uint8_t trimmed_mask;
} pwr_t;

void pwr_init(pwr_t* p, const pwr_cfg_t* cfg);
void pwr_step(pwr_t* p, uint32_t now_ms);     /* call every 1 ms */
void pwr_request_up(pwr_t* p, bool up);
void pwr_request_tx(pwr_t* p, bool on);
void pwr_clear_faults(pwr_t* p);
void pwr_fault(pwr_t* p, uint32_t fault_bits); /* immediate safe-state */
extern const pwr_cfg_t PWR_CFG_DEFAULT;

/* ---------------- thermal management (thermal.c) -------------------------- */
typedef struct {
    int32_t backoff_start_c10;  /* begin TX back-off (PA pedestal)              */
    int32_t backoff_full_c10;   /* full back-off reached                        */
    int32_t backoff_max_db10;   /* maximum TX back-off                          */
    int32_t pa_trip_c10;        /* TX off                                       */
    int32_t pa_restart_c10;     /* hysteresis                                   */
    int32_t versal_trip_c10;
    int32_t heater_on_c10, heater_off_c10;
    int32_t cold_tx_inhibit_c10;
} thermal_cfg_t;

typedef struct {
    int32_t t_pa_max_c10;
    int32_t backoff_db10;
    bool pa_overtemp;
    bool versal_overtemp;
    bool heater_on;
    bool cold_inhibit;
} thermal_t;

extern const thermal_cfg_t THERMAL_CFG_DEFAULT;
void thermal_step(thermal_t* t, const thermal_cfg_t* cfg);   /* call every 100 ms */

/* ---------------- built-in test (bit.c) ----------------------------------- */
typedef struct {
    uint32_t warnings;
    uint32_t faults;
} bit_t;
void bit_step(bit_t* b, const pwr_t* p);                      /* call every 100 ms */

/* ---------------- Versal link (link.c) ------------------------------------ */
typedef struct {
    uint8_t rx[256];
    int rx_len;
    uint32_t seq;
    uint32_t last_rx_ms;
    uint32_t rx_frames, rx_crc_err;
} link_t;
void link_init(link_t* l);
/* parse incoming bytes; returns number of commands decoded into cmds[] */
int link_poll(link_t* l, hg1_mcu_cmd_t* cmds, int max_cmds, uint32_t now_ms);
void link_send_status(link_t* l, const hg1_mcu_status_t* st, uint32_t now_ms);
/* COBS framing helpers (exposed for tests) */
int cobs_encode(const uint8_t* in, int n, uint8_t* out);
int cobs_decode(const uint8_t* in, int n, uint8_t* out);

/* ---------------- application (app.c) -------------------------------------- */
typedef struct {
    pwr_t pwr;
    thermal_t th;
    bit_t bit;
    link_t link;
    uint32_t last_10ms, last_100ms, last_1s, uptime_s;
    uint32_t link_timeout_ms;
    bool host_tx;               /* Versal requested emission */
} app_t;
void app_init(app_t* a);
void app_tick_1ms(app_t* a, uint32_t now_ms);
void app_fill_status(const app_t* a, hg1_mcu_status_t* st);

#endif
