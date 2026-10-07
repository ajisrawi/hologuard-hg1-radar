/* HoloGuard HG-1 -- MCU <-> Versal UART link.
 * Frame = COBS( hg1_hdr_t | payload | CRC-32 ) followed by 0x00.
 */
#include <string.h>

#include "hg1_mcu.h"

int cobs_encode(const uint8_t* in, int n, uint8_t* out) {
    int o = 1, code_pos = 0;
    uint8_t code = 1;
    for (int i = 0; i < n; ++i) {
        if (in[i] == 0) {
            out[code_pos] = code;
            code_pos = o++;
            code = 1;
        } else {
            out[o++] = in[i];
            if (++code == 0xFF) {
                out[code_pos] = code;
                code_pos = o++;
                code = 1;
            }
        }
    }
    out[code_pos] = code;
    return o;
}

int cobs_decode(const uint8_t* in, int n, uint8_t* out) {
    int i = 0, o = 0;
    while (i < n) {
        uint8_t code = in[i++];
        if (code == 0) return -1;
        for (int k = 1; k < code; ++k) {
            if (i >= n) return -1;
            out[o++] = in[i++];
        }
        if (code != 0xFF && i < n) out[o++] = 0;
    }
    return o;
}

void link_init(link_t* l) { memset(l, 0, sizeof(*l)); }

static int handle_frame(link_t* l, const uint8_t* enc, int n, hg1_mcu_cmd_t* cmds, int max, uint32_t now) {
    uint8_t raw[256];
    int m = cobs_decode(enc, n, raw);
    if (m < (int)(sizeof(hg1_hdr_t) + 4)) return 0;
    uint32_t crc;
    memcpy(&crc, raw + m - 4, 4);
    if (crc != hg1_crc32(raw, (size_t)(m - 4))) { ++l->rx_crc_err; return 0; }
    hg1_hdr_t h;
    memcpy(&h, raw, sizeof(h));
    if (h.sync != HG1_SYNC || h.type != HG1_MSG_MCU_CMD || h.len != sizeof(hg1_mcu_cmd_t)) return 0;
    if (max < 1) return 0;
    memcpy(&cmds[0], raw + sizeof(h), sizeof(hg1_mcu_cmd_t));
    ++l->rx_frames;
    l->last_rx_ms = now;
    return 1;
}

int link_poll(link_t* l, hg1_mcu_cmd_t* cmds, int max_cmds, uint32_t now) {
    uint8_t buf[128];
    int got = 0, n;
    while ((n = bsp_link_read(buf, (int)sizeof(buf))) > 0) {
        for (int i = 0; i < n; ++i) {
            if (buf[i] == 0) {
                if (l->rx_len > 0 && got < max_cmds)
                    got += handle_frame(l, l->rx, l->rx_len, cmds + got, max_cmds - got, now);
                l->rx_len = 0;
            } else if (l->rx_len < (int)sizeof(l->rx)) {
                l->rx[l->rx_len++] = buf[i];
            } else {
                l->rx_len = 0;   /* overflow: resync on next delimiter */
            }
        }
    }
    return got;
}

void link_send_status(link_t* l, const hg1_mcu_status_t* st, uint32_t now) {
    uint8_t raw[sizeof(hg1_hdr_t) + sizeof(hg1_mcu_status_t) + 4];
    uint8_t enc[sizeof(raw) + sizeof(raw) / 254 + 3];
    hg1_hdr_t h = {HG1_SYNC, HG1_PROTO_VER, HG1_MSG_MCU_STATUS, (uint16_t)sizeof(*st), l->seq++,
                   (uint64_t)now * 1000u};
    memcpy(raw, &h, sizeof(h));
    memcpy(raw + sizeof(h), st, sizeof(*st));
    uint32_t crc = hg1_crc32(raw, sizeof(h) + sizeof(*st));
    memcpy(raw + sizeof(h) + sizeof(*st), &crc, 4);
    int n = cobs_encode(raw, (int)sizeof(raw), enc);
    enc[n++] = 0;
    bsp_link_write(enc, n);
}
