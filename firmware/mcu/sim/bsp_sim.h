#ifndef HG1_BSP_SIM_H
#define HG1_BSP_SIM_H
#include "bsp.h"

#define SIM_LOG 256

typedef struct {
    uint32_t t;
    int what;
    bool on;
    double vneg;
    int gates_parked;
} sim_event_t;

typedef struct {
    uint32_t now;
    double rail[RAIL_COUNT];
    bool en[EN_COUNT];
    int32_t vg_set[HG1_N_PA];
    double vth_mv[HG1_N_PA];
    double peak_id_ma[HG1_N_PA];
    double vin, ambient_c10, t_pa_c10;
    bool neg_fail, pll_unlock, force_pa_temp, rfic_c10_override;
    int32_t forced_pa_c10, rfic_c10, versal_extra_c10;
    int32_t atten_db10;
    uint32_t wdg_kicks, unsafe_events;
    sim_event_t log[SIM_LOG];
    int nlog;
    uint8_t tx_buf[65536];
    int tx_len;
    uint8_t rx_buf[4096];
    int rx_len, rx_pos;
} sim_t;

void sim_reset(void);
sim_t* sim_state(void);
void sim_advance_ms(uint32_t ms);
double sim_pa_current(int i);
void sim_inject_rx(const uint8_t* b, int n);

#endif
