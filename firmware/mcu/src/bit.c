/* HoloGuard HG-1 -- continuous built-in test (CBIT). */
#include <stdlib.h>

#include "hg1_mcu.h"

static bool in_window(int32_t v, int32_t nom, int32_t pct) {
    return labs(v - nom) * 100 <= (long)labs(nom) * pct;
}

void bit_step(bit_t* b, const pwr_t* p) {
    uint32_t w = 0, f = 0;
    int32_t vin = bsp_rail_mv(RAIL_VIN);
    if (vin < 10500) f |= FAULT_INPUT_UV;            /* below 12 V -12 % */
    else if (vin < 11000) w |= FAULT_INPUT_UV;
    if (bsp_enabled(EN_RF_5V)) {
        if (!in_window(bsp_rail_mv(RAIL_5V), 5000, 5)) f |= FAULT_RAIL_5V;
        if (!in_window(bsp_rail_mv(RAIL_3V3), 3300, 5)) f |= FAULT_RAIL_3V3;
    }
    if (p->state == PWR_READY && !bsp_pll_locked()) w |= FAULT_PLL_UNLOCK;
    if (p->state == PWR_READY) {
        for (int i = 0; i < HG1_N_PA; ++i) {
            int32_t id = bsp_pa_idrain_ma(i);
            /* with TX muted the PA sits at Idq: a drift flags gate-DAC or device ageing */
            if (!p->tx_on && labs(id - PWR_CFG_DEFAULT.idq_target_ma) > 3 * PWR_CFG_DEFAULT.idq_tol_ma)
                w |= FAULT_IDQ_TRIM;
        }
    }
    b->warnings = w;
    b->faults |= f;
}
