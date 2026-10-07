/* HoloGuard HG-1 -- host model of the housekeeping hardware for unit tests.
 * Rails are first-order (tau 2 ms) toward their set-point when enabled.
 * GaN drain current: Id = 50 mA * exp((Vg - Vth_i)/120 mV), Vth_i spread
 * +-80 mV across PAs; with the -5 V rail absent the gates float to ~0 V
 * and the devices go to full channel current (the hazard we test against).
 */
#include <math.h>
#include <string.h>

#include "bsp_sim.h"

static sim_t S;

void sim_reset(void) {
    memset(&S, 0, sizeof(S));
    S.vin = 24000;
    S.ambient_c10 = 250;
    const double vth[HG1_N_PA] = {-2600, -2680, -2540, -2620, -2560, -2660};
    for (int i = 0; i < HG1_N_PA; ++i) { S.vth_mv[i] = vth[i]; S.vg_set[i] = -4000; }
    S.rail[RAIL_VIN] = S.vin;
    S.t_pa_c10 = S.ambient_c10;
}
sim_t* sim_state(void) { return &S; }

static double target(bsp_rail_t r) {
    switch (r) {
    case RAIL_VIN: return S.vin;
    case RAIL_28V: return S.en[EN_28V] ? 28000.0 : 0.0;
    case RAIL_5V: return S.en[EN_RF_5V] ? 5000.0 : 0.0;
    case RAIL_3V3: return S.en[EN_RF_5V] ? 3300.0 : 0.0;
    case RAIL_NEG5: return (S.en[EN_NEG5] && !S.neg_fail) ? -5000.0 : 0.0;
    default: return 0.0;
    }
}

double sim_pa_current(int i) {
    if (!S.en[EN_DRAIN_SW] || S.rail[RAIL_28V] < 1000.0) return 0.0;
    double vg = S.rail[RAIL_NEG5] > -3000.0 ? 0.0 : (double)S.vg_set[i];   /* gate floats without -5 V */
    double id = 50.0 * exp((vg - S.vth_mv[i]) / 120.0);
    if (S.en[EN_TX_MUTE_N]) id += 330.0;                                  /* RF drive, class-AB */
    id *= S.rail[RAIL_28V] / 28000.0;
    return id > 1600.0 ? 1600.0 : id;
}

void sim_advance_ms(uint32_t ms) {
    for (uint32_t k = 0; k < ms; ++k) {
        S.now++;
        for (int r = 0; r < RAIL_COUNT; ++r) S.rail[r] += (target((bsp_rail_t)r) - S.rail[r]) * (1.0 - exp(-1.0 / 2.0));
        double p_tx = 0.0;
        for (int i = 0; i < HG1_N_PA; ++i) {
            double id = sim_pa_current(i);
            if (id > S.peak_id_ma[i]) S.peak_id_ma[i] = id;
            p_tx += id * S.rail[RAIL_28V] * 1e-6 * (S.en[EN_TX_MUTE_N] ? 0.70 : 1.0);   /* dissipation, W */
        }
        /* lumped thermal model: pedestal -> housing -> ambient, tau ~ 60 s */
        double t_target = S.ambient_c10 + p_tx * 10.0 * 4.5;   /* 4.5 K/W per PA cluster */
        S.t_pa_c10 += (t_target - S.t_pa_c10) * (1.0 / 60000.0) + (S.force_pa_temp ? 0 : 0);
        if (S.force_pa_temp) S.t_pa_c10 = S.forced_pa_c10;
        if (S.en[EN_DRAIN_SW] && S.rail[RAIL_NEG5] > -3000.0) S.unsafe_events++;
    }
}

/* ---------------- BSP API --------------------------------------------- */
uint32_t bsp_millis(void) { return S.now; }
void bsp_watchdog_kick(void) { S.wdg_kicks++; }
int32_t bsp_rail_mv(bsp_rail_t r) { return (int32_t)lround(S.rail[r]); }
int32_t bsp_pa_idrain_ma(int pa) { return (int32_t)lround(sim_pa_current(pa)); }
int32_t bsp_temp_c10(bsp_temp_t s) {
    if (s < TS_RFIC) return (int32_t)S.t_pa_c10 + 10 * s;     /* slight spread across PAs */
    if (s == TS_RFIC) return S.rfic_c10_override ? S.rfic_c10 : (int32_t)S.ambient_c10 + 120;
    if (s == TS_VERSAL) return (int32_t)S.ambient_c10 + 250 + S.versal_extra_c10;
    return (int32_t)S.ambient_c10 + 60;
}
void bsp_enable(bsp_enable_t e, bool on) {
    if (S.en[e] != on) {
        S.log[S.nlog % SIM_LOG].t = S.now;
        S.log[S.nlog % SIM_LOG].what = (int)e;
        S.log[S.nlog % SIM_LOG].on = on;
        S.log[S.nlog % SIM_LOG].vneg = S.rail[RAIL_NEG5];
        int park = 1;
        for (int i = 0; i < HG1_N_PA; ++i) if (S.vg_set[i] > -3950) park = 0;
        S.log[S.nlog % SIM_LOG].gates_parked = park;
        S.nlog++;
    }
    S.en[e] = on;
}
bool bsp_enabled(bsp_enable_t e) { return S.en[e]; }
void bsp_pa_gate_mv(int pa, int32_t mv) { S.vg_set[pa] = mv; }
int32_t bsp_pa_gate_get_mv(int pa) { return S.vg_set[pa]; }
void bsp_tx_atten_db10(int32_t db10) { S.atten_db10 = db10; }
bool bsp_pll_locked(void) { return !S.pll_unlock; }
bool bsp_neg_rail_pgood(void) { return S.rail[RAIL_NEG5] < -4500.0; }

int bsp_link_write(const uint8_t* buf, int n) {
    if (S.tx_len + n <= (int)sizeof(S.tx_buf)) { memcpy(S.tx_buf + S.tx_len, buf, (size_t)n); S.tx_len += n; }
    return n;
}
int bsp_link_read(uint8_t* buf, int max) {
    int n = S.rx_len - S.rx_pos;
    if (n > max) n = max;
    if (n <= 0) return 0;
    memcpy(buf, S.rx_buf + S.rx_pos, (size_t)n);
    S.rx_pos += n;
    if (S.rx_pos == S.rx_len) S.rx_pos = S.rx_len = 0;
    return n;
}
void sim_inject_rx(const uint8_t* b, int n) {
    memcpy(S.rx_buf + S.rx_len, b, (size_t)n);
    S.rx_len += n;
}
