/* HoloGuard HG-1 -- housekeeping application: cooperative 1 kHz scheduler.
 *   1 ms   : GaN power sequencer + protection
 *   10 ms  : Versal link (commands), TX gating
 *   100 ms : thermal management, CBIT, status report
 * Emission policy: TX only when the Versal heart-beats (<= 2 s), the PA
 * pedestals are below trip, the RF section is warm enough and no fault is
 * latched -- the radar never radiates unsupervised.
 */
#include <string.h>

#include "hg1_mcu.h"

void app_init(app_t* a) {
    memset(a, 0, sizeof(*a));
    pwr_init(&a->pwr, &PWR_CFG_DEFAULT);
    link_init(&a->link);
    a->link_timeout_ms = 2000;
    bsp_enable(EN_VERSAL, true);
}


static void handle_cmd(app_t* a, const hg1_mcu_cmd_t* c) {
    switch (c->code) {
    case MCU_CMD_POWER_UP: pwr_request_up(&a->pwr, true); break;
    case MCU_CMD_POWER_DOWN: pwr_request_up(&a->pwr, false); a->host_tx = false; break;
    case MCU_CMD_TX_ENABLE: a->host_tx = true; break;
    case MCU_CMD_TX_DISABLE: a->host_tx = false; break;
    case MCU_CMD_CLEAR_FAULTS: a->bit.faults = 0; pwr_clear_faults(&a->pwr); break;
    case MCU_CMD_HEARTBEAT: default: break;
    }
}

void app_fill_status(const app_t* a, hg1_mcu_status_t* st) {
    memset(st, 0, sizeof(*st));
    st->pwr_state = a->pwr.state;
    st->tx_enabled = a->pwr.tx_on;
    st->tx_backoff_db10 = (int8_t)(-a->th.backoff_db10);
    st->heater_on = a->th.heater_on;
    st->faults = a->pwr.faults | a->bit.faults;
    st->warnings = a->bit.warnings;
    st->vin_mv = (uint16_t)bsp_rail_mv(RAIL_VIN);
    st->v28_mv = (uint16_t)bsp_rail_mv(RAIL_28V);
    st->v5_mv = (uint16_t)bsp_rail_mv(RAIL_5V);
    st->v3v3_mv = (uint16_t)bsp_rail_mv(RAIL_3V3);
    st->vneg_mv = (int16_t)bsp_rail_mv(RAIL_NEG5);
    for (int i = 0; i < HG1_N_PA; ++i) {
        st->idq_ma[i] = (uint16_t)bsp_pa_idrain_ma(i);
        st->vg_mv[i] = (int16_t)a->pwr.vg_mv[i];
        st->t_pa_c10[i] = (int16_t)bsp_temp_c10((bsp_temp_t)(TS_PA0 + i));
    }
    st->t_rfic_c10 = (int16_t)bsp_temp_c10(TS_RFIC);
    st->t_versal_c10 = (int16_t)bsp_temp_c10(TS_VERSAL);
    st->t_housing_c10 = (int16_t)bsp_temp_c10(TS_HOUSING);
    st->uptime_s = a->uptime_s;
}

void app_tick_1ms(app_t* a, uint32_t now) {
    pwr_step(&a->pwr, now);

    if (now - a->last_10ms >= 10) {
        a->last_10ms = now;
        hg1_mcu_cmd_t cmds[4];
        int n = link_poll(&a->link, cmds, 4, now);
        for (int i = 0; i < n; ++i) handle_cmd(a, &cmds[i]);
        const bool link_ok = a->link.rx_frames > 0 && (now - a->link.last_rx_ms) <= a->link_timeout_ms;
        const bool allow = a->host_tx && link_ok && !a->th.pa_overtemp && !a->th.cold_inhibit &&
                           !a->bit.faults && !a->pwr.faults;
        pwr_request_tx(&a->pwr, allow);
        if (!link_ok && a->host_tx) a->bit.warnings |= FAULT_LINK_LOST;
    }

    if (now - a->last_100ms >= 100) {
        a->last_100ms = now;
        thermal_step(&a->th, &THERMAL_CFG_DEFAULT);
        bit_step(&a->bit, &a->pwr);
        if (a->th.versal_overtemp) a->bit.faults |= FAULT_VERSAL_OT;
        if (a->bit.faults & (FAULT_RAIL_5V | FAULT_RAIL_3V3 | FAULT_INPUT_UV))
            if (a->pwr.state != PWR_OFF && a->pwr.state != PWR_FAULT) pwr_fault(&a->pwr, a->bit.faults);
        hg1_mcu_status_t st;
        app_fill_status(a, &st);
        link_send_status(&a->link, &st, now);
    }
    if (now - a->last_1s >= 1000) {
        a->last_1s = now;
        ++a->uptime_s;
    }
    bsp_watchdog_kick();
}
