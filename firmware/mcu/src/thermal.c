/* HoloGuard HG-1 -- thermal management.
 * Full performance to +60 degC PA pedestal; linear TX back-off (ADAR1000
 * attenuation, up to 3 dB) to +80 degC; TX off at +95 degC (GaN channel then
 * ~ +175 degC), restart below +85 degC. Cold start: heater on below -30 degC,
 * TX inhibited until the RF section is above -40 degC (LO/VCO lock margin).
 */
#include "hg1_mcu.h"

const thermal_cfg_t THERMAL_CFG_DEFAULT = {
    .backoff_start_c10 = 600,
    .backoff_full_c10 = 800,
    .backoff_max_db10 = 30,
    .pa_trip_c10 = 950,
    .pa_restart_c10 = 850,
    .versal_trip_c10 = 1000,
    .heater_on_c10 = -300,
    .heater_off_c10 = -200,
    .cold_tx_inhibit_c10 = -400,
};

void thermal_step(thermal_t* t, const thermal_cfg_t* c) {
    int32_t tmax = -1000;
    for (int i = 0; i < HG1_N_PA; ++i) {
        int32_t v = bsp_temp_c10((bsp_temp_t)(TS_PA0 + i));
        if (v > tmax) tmax = v;
    }
    t->t_pa_max_c10 = tmax;

    if (tmax <= c->backoff_start_c10) t->backoff_db10 = 0;
    else if (tmax >= c->backoff_full_c10) t->backoff_db10 = c->backoff_max_db10;
    else t->backoff_db10 = (tmax - c->backoff_start_c10) * c->backoff_max_db10 /
                           (c->backoff_full_c10 - c->backoff_start_c10);
    bsp_tx_atten_db10(t->backoff_db10);

    if (!t->pa_overtemp && tmax >= c->pa_trip_c10) t->pa_overtemp = true;
    else if (t->pa_overtemp && tmax <= c->pa_restart_c10) t->pa_overtemp = false;

    t->versal_overtemp = bsp_temp_c10(TS_VERSAL) >= c->versal_trip_c10;

    int32_t th = bsp_temp_c10(TS_HOUSING);
    if (!t->heater_on && th <= c->heater_on_c10) t->heater_on = true;
    else if (t->heater_on && th >= c->heater_off_c10) t->heater_on = false;
    bsp_enable(EN_HEATER, t->heater_on);

    t->cold_inhibit = bsp_temp_c10(TS_RFIC) < c->cold_tx_inhibit_c10;
}
