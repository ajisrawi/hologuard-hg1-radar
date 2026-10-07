/* HoloGuard HG-1 housekeeping firmware -- host unit tests against bsp_sim.
 * Each test drives the real application (app.c / power_seq.c / thermal.c /
 * bit.c / link.c) through the simulated hardware and checks the GaN safety
 * invariants and protocol behaviour.
 */
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "bsp_sim.h"
#include "hg1_mcu.h"

static int g_fail = 0, g_pass = 0;
#define CHECK(cond, ...)                                              \
    do {                                                              \
        if (cond) { ++g_pass; }                                       \
        else { ++g_fail; printf("  FAIL %s:%d  ", __FILE__, __LINE__); \
               printf(__VA_ARGS__); printf("\n"); }                   \
    } while (0)

static void send_cmd(uint8_t code) {
    static uint32_t seq = 0;
    hg1_mcu_cmd_t c = {code, 0, 0};
    uint8_t raw[sizeof(hg1_hdr_t) + sizeof(c) + 4], enc[64];
    hg1_hdr_t h = {HG1_SYNC, HG1_PROTO_VER, HG1_MSG_MCU_CMD, sizeof(c), seq++, 0};
    memcpy(raw, &h, sizeof(h));
    memcpy(raw + sizeof(h), &c, sizeof(c));
    uint32_t crc = hg1_crc32(raw, sizeof(h) + sizeof(c));
    memcpy(raw + sizeof(h) + sizeof(c), &crc, 4);
    int n = cobs_encode(raw, (int)sizeof(raw), enc);
    enc[n++] = 0;
    sim_inject_rx(enc, n);
}

static void run(app_t* a, uint32_t ms, bool heartbeat) {
    for (uint32_t i = 0; i < ms; ++i) {
        if (heartbeat && sim_state()->now % 200 == 0) send_cmd(MCU_CMD_HEARTBEAT);
        sim_advance_ms(1);
        app_tick_1ms(a, sim_state()->now);
    }
}

static int find_event(int what, bool on) {
    sim_t* S = sim_state();
    for (int i = 0; i < S->nlog && i < SIM_LOG; ++i)
        if (S->log[i].what == what && S->log[i].on == on) return i;
    return -1;
}

/* ---------------------------------------------------------------------- */
static void test_powerup_order(void) {
    printf("test_powerup_order\n");
    sim_reset();
    app_t a;
    app_init(&a);
    send_cmd(MCU_CMD_POWER_UP);
    run(&a, 600, true);
    sim_t* S = sim_state();
    int i_neg = find_event(EN_NEG5, true), i_28 = find_event(EN_28V, true), i_sw = find_event(EN_DRAIN_SW, true);
    CHECK(i_neg >= 0 && i_28 > i_neg && i_sw > i_28, "order neg(%d) < 28V(%d) < drain(%d)", i_neg, i_28, i_sw);
    CHECK(i_sw >= 0 && S->log[i_sw].vneg < -4700.0, "-5 V present at drain enable (%.0f mV)", S->log[i_sw].vneg);
    CHECK(i_sw >= 0 && S->log[i_sw].gates_parked, "gates at pinch-off when drain switched on");
    CHECK(a.pwr.state == PWR_READY, "reached READY (state %d)", a.pwr.state);
    for (int i = 0; i < HG1_N_PA; ++i) {
        int32_t id = bsp_pa_idrain_ma(i);
        CHECK(fabs(id - 50.0) <= 6.0, "PA%d Idq %d mA trimmed to 50+-6", i, (int)id);
    }
    CHECK(S->unsafe_events == 0, "no drain-without-gate-bias interval (%u ms)", S->unsafe_events);
    printf("  READY after %u ms, Vg = [%d %d %d %d %d %d] mV\n", (unsigned)a.pwr.t_state,
           (int)a.pwr.vg_mv[0], (int)a.pwr.vg_mv[1], (int)a.pwr.vg_mv[2], (int)a.pwr.vg_mv[3],
           (int)a.pwr.vg_mv[4], (int)a.pwr.vg_mv[5]);
}

static void test_tx_requires_heartbeat(void) {
    printf("test_tx_requires_heartbeat\n");
    sim_reset();
    app_t a;
    app_init(&a);
    send_cmd(MCU_CMD_POWER_UP);
    run(&a, 600, true);
    send_cmd(MCU_CMD_TX_ENABLE);
    run(&a, 50, true);
    CHECK(a.pwr.tx_on && bsp_enabled(EN_TX_MUTE_N), "TX on with heartbeat");
    run(&a, 2300, false);                         /* Versal goes silent */
    CHECK(!a.pwr.tx_on && !bsp_enabled(EN_TX_MUTE_N), "TX muted after heartbeat loss");
    CHECK(a.bit.warnings & FAULT_LINK_LOST, "link-lost warning raised");
}

static void test_neg_rail_loss(void) {
    printf("test_neg_rail_loss\n");
    sim_reset();
    app_t a;
    app_init(&a);
    send_cmd(MCU_CMD_POWER_UP);
    send_cmd(MCU_CMD_TX_ENABLE);
    run(&a, 700, true);
    CHECK(a.pwr.state == PWR_READY && a.pwr.tx_on, "precondition: READY + TX");
    sim_state()->neg_fail = true;                 /* LT3462 dies */
    uint32_t t0 = sim_state()->now, t_off = 0;
    for (int i = 0; i < 50; ++i) {
        run(&a, 1, true);
        if (!bsp_enabled(EN_DRAIN_SW) && !t_off) t_off = sim_state()->now - t0;
    }
    CHECK(a.pwr.faults & FAULT_NEG_RAIL, "FAULT_NEG_RAIL latched");
    CHECK(t_off > 0 && t_off <= 2, "drain removed within %u ms of rail collapse", t_off);
    CHECK(!bsp_enabled(EN_TX_MUTE_N), "TX muted");
    CHECK(sim_state()->unsafe_events <= 1, "exposure <= 1 ms (%u)", sim_state()->unsafe_events);
    /* fault is latched: TX enable must not re-arm until cleared and rail healthy */
    send_cmd(MCU_CMD_TX_ENABLE);
    run(&a, 100, true);
    CHECK(!a.pwr.tx_on, "stays safe while fault latched");
}

static void test_thermal_backoff(void) {
    printf("test_thermal_backoff\n");
    sim_reset();
    app_t a;
    app_init(&a);
    send_cmd(MCU_CMD_POWER_UP);
    send_cmd(MCU_CMD_TX_ENABLE);
    run(&a, 700, true);
    sim_t* S = sim_state();
    S->force_pa_temp = true;
    S->forced_pa_c10 = 700;                         /* 70 degC (+50 on hottest PA) */
    run(&a, 300, true);
    CHECK(S->atten_db10 > 0 && S->atten_db10 < 30, "partial back-off at 70-75 C (%d x0.1 dB)", (int)S->atten_db10);
    CHECK(a.pwr.tx_on, "still transmitting during back-off");
    S->forced_pa_c10 = 960;
    run(&a, 300, true);
    CHECK(!a.pwr.tx_on, "TX off above trip");
    S->forced_pa_c10 = 900;
    run(&a, 300, true);
    CHECK(!a.pwr.tx_on, "hysteresis: still off at 90 C");
    S->forced_pa_c10 = 800;
    run(&a, 300, true);
    CHECK(a.pwr.tx_on, "TX restored below restart threshold");
}

static void test_cold_start(void) {
    printf("test_cold_start\n");
    sim_reset();
    sim_t* S = sim_state();
    S->ambient_c10 = -450;
    S->t_pa_c10 = -450;
    S->rfic_c10_override = true;
    S->rfic_c10 = -450;
    app_t a;
    app_init(&a);
    send_cmd(MCU_CMD_POWER_UP);
    send_cmd(MCU_CMD_TX_ENABLE);
    run(&a, 700, true);
    CHECK(bsp_enabled(EN_HEATER), "heater on at -45 C");
    CHECK(!a.pwr.tx_on, "TX inhibited while RF section below -40 C");
    S->rfic_c10 = -300;
    run(&a, 300, true);
    CHECK(a.pwr.tx_on, "TX allowed once warm");
}

static void test_shutdown_order(void) {
    printf("test_shutdown_order\n");
    sim_reset();
    app_t a;
    app_init(&a);
    send_cmd(MCU_CMD_POWER_UP);
    run(&a, 600, true);
    sim_state()->nlog = 0;
    send_cmd(MCU_CMD_POWER_DOWN);
    run(&a, 200, true);
    int i_sw = find_event(EN_DRAIN_SW, false), i_neg = find_event(EN_NEG5, false);
    CHECK(i_sw >= 0 && i_neg > i_sw, "drain off (%d) before -5 V off (%d)", i_sw, i_neg);
    CHECK(i_sw >= 0 && sim_state()->log[i_sw].gates_parked, "gates parked before drain removed");
    CHECK(a.pwr.state == PWR_OFF, "back to OFF (%d)", a.pwr.state);
    CHECK(sim_state()->unsafe_events == 0, "no unsafe interval");
}

static void test_link_codec(void) {
    printf("test_link_codec\n");
    uint8_t in[300], enc[320], dec[320];
    for (int i = 0; i < 300; ++i) in[i] = (uint8_t)((i * 37) & 0xFF);   /* includes zeros */
    int n = cobs_encode(in, 300, enc);
    int zeros = 0;
    for (int i = 0; i < n; ++i) zeros += enc[i] == 0;
    CHECK(zeros == 0, "COBS output has no zero bytes");
    int m = cobs_decode(enc, n, dec);
    CHECK(m == 300 && memcmp(in, dec, 300) == 0, "COBS round-trip (%d bytes)", m);
    CHECK(hg1_crc32("123456789", 9) == 0xCBF43926u, "CRC-32 check value");

    sim_reset();
    app_t a;
    app_init(&a);
    run(&a, 250, true);
    sim_t* S = sim_state();
    /* decode the last status frame the MCU emitted */
    int end = S->tx_len - 1, start = end - 1;
    while (start > 0 && S->tx_buf[start - 1] != 0) --start;
    m = cobs_decode(S->tx_buf + start, end - start, dec);
    hg1_hdr_t h;
    memcpy(&h, dec, sizeof(h));
    uint32_t crc;
    memcpy(&crc, dec + m - 4, 4);
    CHECK(h.sync == HG1_SYNC && h.type == HG1_MSG_MCU_STATUS && h.len == sizeof(hg1_mcu_status_t),
          "status frame header");
    CHECK(crc == hg1_crc32(dec, (size_t)(m - 4)), "status frame CRC");
    CHECK(a.link.rx_frames > 0 && a.link.rx_crc_err == 0, "commands decoded (%u), no CRC errors",
          a.link.rx_frames);
}

int main(void) {
    test_powerup_order();
    test_tx_requires_heartbeat();
    test_neg_rail_loss();
    test_thermal_backoff();
    test_cold_start();
    test_shutdown_order();
    test_link_codec();
    printf("\n%d checks passed, %d failed\n", g_pass, g_fail);
    return g_fail ? 1 : 0;
}
