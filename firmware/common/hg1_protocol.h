/* HoloGuard HG-1 -- external (Ethernet/UDP) and internal (MCU<->Versal UART)
 * message definitions. Little-endian, packed. Every frame:
 *   hg1_hdr_t | payload | CRC-32 (IEEE 802.3, over hdr+payload)
 * C11 / C++ compatible; shared by the Versal APU daemon and the STM32 MCU.
 */
#ifndef HG1_PROTOCOL_H
#define HG1_PROTOCOL_H
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define HG1_SYNC 0x52314748u /* "HG1R" */
#define HG1_PROTO_VER 1u

enum hg1_msg_type {
    HG1_MSG_PLOTS = 0x01,       /* raw 3-D/4-D detections of one CPI        */
    HG1_MSG_TRACKS = 0x02,      /* track table                               */
    HG1_MSG_STATUS = 0x03,      /* radar health (APU + MCU)                  */
    HG1_MSG_SPOTLIGHT = 0x04,   /* active GaN spotlight                       */
    HG1_MSG_CMD = 0x10,         /* command to radar                          */
    HG1_MSG_MCU_STATUS = 0x20,  /* internal: MCU -> Versal                   */
    HG1_MSG_MCU_CMD = 0x21      /* internal: Versal -> MCU                   */
};

#pragma pack(push, 1)
typedef struct {
    uint32_t sync;
    uint8_t ver;
    uint8_t type;
    uint16_t len;          /* payload bytes */
    uint32_t seq;
    uint64_t t_us;         /* PTP / GNSS-disciplined time, microseconds */
} hg1_hdr_t;

typedef struct {
    float range_m, az_deg, el_deg, vr_mps;
    float snr_db, rcs_dbsm, md_ratio;
} hg1_plot_t;

typedef struct {
    uint32_t id;
    uint8_t cls;           /* holo::TrackClass */
    uint8_t confirmed;
    uint8_t threat_pct;
    uint8_t reserved;
    float x_m, y_m, z_m;   /* radar frame: x right, y boresight, z up */
    float vx, vy, vz;
    float range_m, az_deg, el_deg;
    float sigma_pos_m, rcs_dbsm, md_ratio;
} hg1_track_t;

typedef struct {
    uint32_t track_id;
    float az_deg, el_deg, gain_db;
    uint8_t phase_code[6];
    uint8_t active;
    uint8_t reserved;
} hg1_spotlight_t;

/* ---- internal MCU link ------------------------------------------------ */
enum hg1_pwr_state {
    PWR_OFF = 0, PWR_NEG_RAIL, PWR_PINCHOFF, PWR_DRAIN_RAMP, PWR_BIAS_TRIM, PWR_READY,
    PWR_SHUTDOWN, PWR_FAULT
};

enum hg1_fault_bits {
    FAULT_NEG_RAIL = 1u << 0, FAULT_DRAIN_UV = 1u << 1, FAULT_DRAIN_OV = 1u << 2,
    FAULT_PA_OC = 1u << 3, FAULT_PA_OT = 1u << 4, FAULT_IDQ_TRIM = 1u << 5,
    FAULT_RAIL_5V = 1u << 6, FAULT_RAIL_3V3 = 1u << 7, FAULT_PLL_UNLOCK = 1u << 8,
    FAULT_VERSAL_OT = 1u << 9, FAULT_INPUT_UV = 1u << 10, FAULT_LINK_LOST = 1u << 11,
    FAULT_WATCHDOG = 1u << 12
};

typedef struct {
    uint8_t pwr_state;     /* hg1_pwr_state */
    uint8_t tx_enabled;
    int8_t tx_backoff_db10; /* commanded TX back-off, 0.1 dB units (negative) */
    uint8_t heater_on;
    uint32_t faults;       /* latched hg1_fault_bits */
    uint32_t warnings;
    uint16_t vin_mv, v28_mv, v5_mv, v3v3_mv;
    int16_t vneg_mv;
    uint16_t idq_ma[6];
    int16_t vg_mv[6];
    int16_t t_pa_c10[6];   /* 0.1 degC */
    int16_t t_rfic_c10, t_versal_c10, t_housing_c10;
    uint32_t uptime_s;
} hg1_mcu_status_t;

enum hg1_mcu_cmd_code {
    MCU_CMD_POWER_UP = 1, MCU_CMD_POWER_DOWN = 2, MCU_CMD_TX_ENABLE = 3, MCU_CMD_TX_DISABLE = 4,
    MCU_CMD_CLEAR_FAULTS = 5, MCU_CMD_SET_IDQ_MA = 6, MCU_CMD_HEARTBEAT = 7
};

typedef struct {
    uint8_t code;
    uint8_t arg8;
    uint16_t arg16;
} hg1_mcu_cmd_t;
#pragma pack(pop)

/* CRC-32 (reflected 0xEDB88320), table-less for the MCU */
static inline uint32_t hg1_crc32(const void* data, size_t n) {
    const uint8_t* p = (const uint8_t*)data;
    uint32_t c = 0xFFFFFFFFu;
    for (size_t i = 0; i < n; ++i) {
        c ^= p[i];
        for (int k = 0; k < 8; ++k) c = (c >> 1) ^ (0xEDB88320u & (0u - (c & 1u)));
    }
    return ~c;
}

#ifdef __cplusplus
}
#endif
#endif /* HG1_PROTOCOL_H */
