/* HoloGuard HG-1 -- GaN PA power sequencing.
 *
 * Depletion-mode GaN HEMTs conduct at Vg = 0 V. The only safe order is:
 *   up  : -5 V gate rail -> gates to pinch-off -> 28 V drain -> trim Vg to Idq
 *   down: TX mute -> gates to pinch-off -> drain off -> discharge -> -5 V off
 * Loss of the negative rail with drain applied destroys the PAs in
 * microseconds, so (a) a hardware comparator on -5 V opens the drain switch
 * independently of firmware, and (b) this state machine re-checks the rail
 * every 1 ms tick and forces the safe state.
 */
#include <string.h>

#include "hg1_mcu.h"

const pwr_cfg_t PWR_CFG_DEFAULT = {
    .vneg_min_mv = -4750,
    .vg_pinchoff_mv = -4000,
    .vg_start_mv = -3300,
    .vg_max_mv = -1800,
    .v28_min_mv = 26500,
    .v28_max_mv = 29500,
    .idq_target_ma = 50,
    .idq_tol_ma = 6,
    .id_max_ma = 650,
    .neg_settle_ms = 5,
    .drain_ramp_ms = 12,
    .trim_timeout_ms = 400,
    .vg_step_mv = 5,
};

static const pwr_cfg_t* C;

static void enter(pwr_t* p, uint8_t s, uint32_t now) {
    p->state = s;
    p->t_state = now;
}

static void gates_to(pwr_t* p, int32_t mv) {
    for (int i = 0; i < HG1_N_PA; ++i) {
        p->vg_mv[i] = mv;
        bsp_pa_gate_mv(i, mv);
    }
}

static bool gates_parked(void) {
    for (int i = 0; i < HG1_N_PA; ++i)
        if (bsp_pa_gate_get_mv(i) > C->vg_pinchoff_mv + 50) return false;
    return true;
}

static bool neg_ok(void) {
    return bsp_neg_rail_pgood() && bsp_rail_mv(RAIL_NEG5) <= C->vneg_min_mv;
}

/* Immediate safe state: no RF, no drain. Gates stay parked while -5 V lives. */
static void safe_state(pwr_t* p) {
    bsp_enable(EN_TX_MUTE_N, false);
    p->tx_on = false;
    bsp_enable(EN_DRAIN_SW, false);
    bsp_enable(EN_28V, false);
    gates_to(p, C->vg_pinchoff_mv);
}

void pwr_init(pwr_t* p, const pwr_cfg_t* cfg) {
    memset(p, 0, sizeof(*p));
    C = cfg ? cfg : &PWR_CFG_DEFAULT;
    safe_state(p);
    bsp_enable(EN_NEG5, false);
    enter(p, PWR_OFF, bsp_millis());
}

void pwr_request_up(pwr_t* p, bool up) { p->up_request = up; }
void pwr_request_tx(pwr_t* p, bool on) { p->tx_request = on; }

void pwr_clear_faults(pwr_t* p) {
    if (p->state == PWR_FAULT && !bsp_enabled(EN_DRAIN_SW)) {
        p->faults = 0;
        enter(p, PWR_OFF, bsp_millis());
    }
}

void pwr_fault(pwr_t* p, uint32_t bits) {
    p->faults |= bits;
    safe_state(p);
    if (p->state != PWR_FAULT) enter(p, PWR_FAULT, bsp_millis());
}

void pwr_step(pwr_t* p, uint32_t now) {
    const uint32_t dt = now - p->t_state;

    /* ---- invariants checked every tick, in every powered state --------- */
    if (bsp_enabled(EN_DRAIN_SW) || bsp_enabled(EN_28V)) {
        if (!neg_ok()) { pwr_fault(p, FAULT_NEG_RAIL); return; }
        if (!gates_parked() && p->state < PWR_BIAS_TRIM) { pwr_fault(p, FAULT_NEG_RAIL); return; }
    }
    if (bsp_enabled(EN_DRAIN_SW)) {
        for (int i = 0; i < HG1_N_PA; ++i)
            if (bsp_pa_idrain_ma(i) > C->id_max_ma) { pwr_fault(p, FAULT_PA_OC); return; }
        int32_t v28 = bsp_rail_mv(RAIL_28V);
        if (v28 > C->v28_max_mv) { pwr_fault(p, FAULT_DRAIN_OV); return; }
        if (p->state >= PWR_BIAS_TRIM && p->state <= PWR_READY && v28 < C->v28_min_mv) {
            pwr_fault(p, FAULT_DRAIN_UV);
            return;
        }
    }

    switch (p->state) {
    case PWR_OFF:
        if (p->up_request && !p->faults) {
            gates_to(p, C->vg_pinchoff_mv);          /* DAC preset before rail exists */
            bsp_enable(EN_RF_5V, true);
            bsp_enable(EN_NEG5, true);
            enter(p, PWR_NEG_RAIL, now);
        }
        break;

    case PWR_NEG_RAIL:
        if (dt >= C->neg_settle_ms && neg_ok()) {
            gates_to(p, C->vg_pinchoff_mv);
            enter(p, PWR_PINCHOFF, now);
        } else if (dt > 50) {
            pwr_fault(p, FAULT_NEG_RAIL);
        }
        break;

    case PWR_PINCHOFF:
        if (gates_parked() && neg_ok()) {
            bsp_enable(EN_28V, true);
            enter(p, PWR_DRAIN_RAMP, now);
        } else if (dt > 20) {
            pwr_fault(p, FAULT_NEG_RAIL);
        }
        break;

    case PWR_DRAIN_RAMP: {
        int32_t v28 = bsp_rail_mv(RAIL_28V);
        if (!bsp_enabled(EN_DRAIN_SW)) {
            if (v28 >= C->v28_min_mv) {
                bsp_enable(EN_DRAIN_SW, true);       /* soft-start switch, pinched gates */
                p->t_state = now;
            } else if (dt > 60) {
                pwr_fault(p, FAULT_DRAIN_UV);
            }
        } else if (dt >= C->drain_ramp_ms) {
            for (int i = 0; i < HG1_N_PA; ++i)
                if (bsp_pa_idrain_ma(i) > 5) { pwr_fault(p, FAULT_IDQ_TRIM); return; }  /* gate leak / short */
            gates_to(p, C->vg_start_mv);
            p->trimmed_mask = 0;
            enter(p, PWR_BIAS_TRIM, now);
        }
        break;
    }

    case PWR_BIAS_TRIM: {
        /* closed-loop Idq trim, 1 step per PA per ms, then hold */
        uint8_t ok = 0;
        for (int i = 0; i < HG1_N_PA; ++i) {
            int32_t id = bsp_pa_idrain_ma(i);
            if (id < C->idq_target_ma - C->idq_tol_ma) {
                if (p->vg_mv[i] + C->vg_step_mv <= C->vg_max_mv) p->vg_mv[i] += C->vg_step_mv;
            } else if (id > C->idq_target_ma + C->idq_tol_ma) {
                p->vg_mv[i] -= C->vg_step_mv;
            } else {
                ok |= (uint8_t)(1u << i);
            }
            bsp_pa_gate_mv(i, p->vg_mv[i]);
        }
        p->trimmed_mask = ok;
        if (ok == (1u << HG1_N_PA) - 1u) enter(p, PWR_READY, now);
        else if (dt > C->trim_timeout_ms) pwr_fault(p, FAULT_IDQ_TRIM);
        break;
    }

    case PWR_READY: {
        bool want = p->tx_request;
        if (want != p->tx_on) {
            bsp_enable(EN_TX_MUTE_N, want);
            p->tx_on = want;
        }
        if (!p->up_request) {
            bsp_enable(EN_TX_MUTE_N, false);
            p->tx_on = false;
            gates_to(p, C->vg_pinchoff_mv);
            enter(p, PWR_SHUTDOWN, now);
        }
        break;
    }

    case PWR_SHUTDOWN:
        if (dt >= 2 && bsp_enabled(EN_DRAIN_SW)) {      /* gates parked for 2 ms first */
            bsp_enable(EN_DRAIN_SW, false);
            bsp_enable(EN_28V, false);
        }
        if (!bsp_enabled(EN_DRAIN_SW) && bsp_rail_mv(RAIL_28V) < 2000) {
            bsp_enable(EN_NEG5, false);                 /* gate rail is the last to go */
            bsp_enable(EN_RF_5V, false);
            enter(p, PWR_OFF, now);
        }
        break;

    case PWR_FAULT:
        /* keep gates biased negative until the drain bulk capacitance is gone */
        if (bsp_rail_mv(RAIL_28V) < 2000 && bsp_enabled(EN_NEG5) && dt > 20) bsp_enable(EN_NEG5, false);
        break;

    default:
        pwr_fault(p, FAULT_WATCHDOG);
        break;
    }
}
