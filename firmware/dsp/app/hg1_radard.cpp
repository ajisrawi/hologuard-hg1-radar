// hg1_radard -- HoloGuard HG-1 radar daemon (Versal APU, Linux / host test bench).
//
// On target: ADC cubes arrive by AXI-DMA from the JESD204B receiver into a
// ping-pong DDR buffer (/dev/hg1_cube via UIO); the AIE/PL accelerators run
// stages 1-4, this process runs CFAR -> plots -> tracker -> spotlight and
// publishes UDP. On the host the same code replays a recorded or simulated
// scenario file (sim/gen_scenario.py) through the full reference chain.
//
//   hg1_radard --input sim/out/scenario.iq --out sim/out [--udp 127.0.0.1:47800]
//              [--profile sim|production]
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "ws2_32.lib")
#else
#include <arpa/inet.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

#include "../../common/hg1_protocol.h"
#include "holo/pipeline.hpp"

using namespace holo;

#pragma pack(push, 1)
struct ScenarioHeader {
    char magic[8];
    uint32_t version, n_frames, n_rx, n_chirps, n_samples;
    double frame_period_s;
};
#pragma pack(pop)

class UdpOut {
public:
    bool open(const std::string& hostport) {
        auto c = hostport.find(':');
        if (c == std::string::npos) return false;
#ifdef _WIN32
        WSADATA w;
        WSAStartup(MAKEWORD(2, 2), &w);
#endif
        sock_ = int(socket(AF_INET, SOCK_DGRAM, 0));
        std::memset(&addr_, 0, sizeof(addr_));
        addr_.sin_family = AF_INET;
        addr_.sin_port = htons(uint16_t(std::stoi(hostport.substr(c + 1))));
        inet_pton(AF_INET, hostport.substr(0, c).c_str(), &addr_.sin_addr);
        return sock_ >= 0;
    }
    void send(const std::vector<uint8_t>& b) {
        if (sock_ >= 0)
            sendto(sock_, reinterpret_cast<const char*>(b.data()), int(b.size()), 0,
                   reinterpret_cast<const sockaddr*>(&addr_), sizeof(addr_));
    }
private:
    int sock_ = -1;
    sockaddr_in addr_{};
};

static std::vector<uint8_t> frame(uint8_t type, uint32_t seq, uint64_t t_us, const void* payload, size_t n) {
    hg1_hdr_t h{HG1_SYNC, HG1_PROTO_VER, type, uint16_t(n), seq, t_us};
    std::vector<uint8_t> b(sizeof(h) + n + 4);
    std::memcpy(b.data(), &h, sizeof(h));
    if (n) std::memcpy(b.data() + sizeof(h), payload, n);
    uint32_t crc = hg1_crc32(b.data(), sizeof(h) + n);
    std::memcpy(b.data() + sizeof(h) + n, &crc, 4);
    return b;
}

static double deg(double r) { return r * 180.0 / kPi; }
// JSON has no inf/nan
static double fin(double v) { return std::isfinite(v) ? v : 0.0; }

int main(int argc, char** argv) {
    std::string input, outdir = ".", udp, profile = "sim";
    for (int i = 1; i + 1 < argc; i += 2) {
        std::string k = argv[i], v = argv[i + 1];
        if (k == "--input") input = v;
        else if (k == "--out") outdir = v;
        else if (k == "--udp") udp = v;
        else if (k == "--profile") profile = v;
    }
    if (input.empty()) {
        std::fprintf(stderr, "usage: hg1_radard --input scenario.iq [--out dir] [--udp host:port]\n");
        return 2;
    }
    std::ifstream f(input, std::ios::binary);
    ScenarioHeader sh{};
    f.read(reinterpret_cast<char*>(&sh), sizeof(sh));
    if (!f || std::strncmp(sh.magic, "HG1IQ", 5) != 0) {
        std::fprintf(stderr, "bad scenario file\n");
        return 1;
    }
    RadarConfig cfg = profile == "production" ? RadarConfig::production() : RadarConfig::sim_long_range();
    if (int(sh.n_rx) != cfg.n_rx() || int(sh.n_chirps) != cfg.n_chirps || int(sh.n_samples) != cfg.n_samples) {
        std::fprintf(stderr, "scenario dimensions do not match profile '%s'\n", profile.c_str());
        return 1;
    }
    std::printf("HG-1 radard: profile=%s  %d RX x %d TX (virtual %d)  %d chirps x %d samples  "
                "dR=%.2f m  Rmax=%.0f m  dV=%.2f m/s  Vamb=+-%.1f m/s\n",
                profile.c_str(), cfg.n_rx(), cfg.n_tx(), cfg.n_rx() * cfg.n_tx(), cfg.n_chirps,
                cfg.n_samples, cfg.range_res(), cfg.r_max(), cfg.vel_res(), cfg.v_unamb());

    SignalProcessor sp(cfg);
    Tracker trk(cfg);
    UdpOut net;
    if (!udp.empty()) net.open(udp);
    std::ofstream js(outdir + "/radard_output.jsonl");
    std::ofstream bin(outdir + "/radard_stream.bin", std::ios::binary);

    std::vector<int16_t> buf(size_t(sh.n_rx) * sh.n_chirps * sh.n_samples * 2);
    uint32_t seq = 0;
    double total_ms = 0;
    for (uint32_t fi = 0; fi < sh.n_frames; ++fi) {
        f.read(reinterpret_cast<char*>(buf.data()), std::streamsize(buf.size() * sizeof(int16_t)));
        if (!f) break;
        const double t = fi * sh.frame_period_s;
        const uint64_t t_us = uint64_t(t * 1e6);
        CpiResult res = sp.process(buf.data());
        trk.update(res.plots, t);
        SpotlightCommand spot = plan_spotlight(cfg, trk.tracks());
        total_ms += res.proc_ms;

        // ---- binary stream (UDP + file)
        std::vector<hg1_plot_t> pl;
        for (const auto& p : res.plots)
            pl.push_back({float(p.range_m), float(deg(p.az_rad)), float(deg(p.el_rad)), float(p.vr_mps),
                          float(p.snr_db), float(p.rcs_dbsm), float(p.md_ratio)});
        std::vector<hg1_track_t> tl;
        for (const auto& t : trk.tracks()) {
            const double r = std::sqrt(t.x[0] * t.x[0] + t.x[1] * t.x[1] + t.x[2] * t.x[2]);
            const double sp_ = std::sqrt(t.P[0] + t.P[7] + t.P[14]);
            tl.push_back({t.id, uint8_t(t.cls), uint8_t(t.confirmed), uint8_t(t.threat * 100), 0,
                          float(t.x[0]), float(t.x[1]), float(t.x[2]), float(t.x[3]), float(t.x[4]),
                          float(t.x[5]), float(r), float(deg(std::atan2(t.x[0], t.x[1]))),
                          float(deg(std::asin(t.x[2] / std::max(r, 1.0)))), float(sp_), float(t.rcs_avg),
                          float(t.md_avg)});
        }
        hg1_spotlight_t sl{spot.track_id, float(deg(spot.az_rad)), float(deg(spot.el_rad)), float(spot.gain_db),
                           {}, uint8_t(spot.active), 0};
        std::memcpy(sl.phase_code, spot.phase_code.data(), 6);
        for (auto& b : {frame(HG1_MSG_PLOTS, seq++, t_us, pl.data(), pl.size() * sizeof(hg1_plot_t)),
                        frame(HG1_MSG_TRACKS, seq++, t_us, tl.data(), tl.size() * sizeof(hg1_track_t)),
                        frame(HG1_MSG_SPOTLIGHT, seq++, t_us, &sl, sizeof(sl))}) {
            bin.write(reinterpret_cast<const char*>(b.data()), std::streamsize(b.size()));
            net.send(b);
        }

        // ---- JSON lines (debug / verification)
        js << "{\"frame\":" << fi << ",\"t\":" << t << ",\"proc_ms\":" << res.proc_ms
           << ",\"noise_db\":" << res.noise_floor_db << ",\"plots\":[";
        for (size_t i = 0; i < res.plots.size(); ++i) {
            const auto& p = res.plots[i];
            js << (i ? "," : "") << "{\"r\":" << p.range_m << ",\"az\":" << deg(p.az_rad) << ",\"el\":"
               << deg(p.el_rad) << ",\"vr\":" << p.vr_mps << ",\"snr\":" << fin(p.snr_db) << ",\"rcs\":" << fin(p.rcs_dbsm)
               << ",\"md\":" << fin(p.md_ratio) << "}";
        }
        js << "],\"tracks\":[";
        bool first = true;
        for (const auto& t : trk.tracks()) {
            if (!t.confirmed) continue;
            const double r = std::sqrt(t.x[0] * t.x[0] + t.x[1] * t.x[1] + t.x[2] * t.x[2]);
            js << (first ? "" : ",") << "{\"id\":" << t.id << ",\"cls\":\"" << to_string(t.cls)
               << "\",\"x\":" << t.x[0] << ",\"y\":" << t.x[1] << ",\"z\":" << t.x[2] << ",\"vx\":" << t.x[3]
               << ",\"vy\":" << t.x[4] << ",\"vz\":" << t.x[5] << ",\"r\":" << r << ",\"threat\":" << t.threat
               << ",\"md\":" << fin(t.md_avg) << ",\"rcs\":" << fin(t.rcs_avg) << "}";
            first = false;
        }
        js << "],\"spotlight\":{\"active\":" << (spot.active ? "true" : "false") << ",\"track\":" << spot.track_id
           << ",\"az\":" << deg(spot.az_rad) << ",\"el\":" << deg(spot.el_rad) << ",\"phase\":[";
        for (int k = 0; k < 6; ++k) js << (k ? "," : "") << int(spot.phase_code[k]);
        js << "]}}\n";

        int nconf = 0;
        for (const auto& t : trk.tracks()) nconf += t.confirmed;
        std::printf("frame %3u  t=%5.2fs  plots %2zu  tracks %2d  proc %6.1f ms%s\n", fi, t, res.plots.size(),
                    nconf, res.proc_ms, spot.active ? "  [spotlight]" : "");
    }
    std::printf("mean processing time per CPI: %.1f ms\n", total_ms / std::max<uint32_t>(1, sh.n_frames));
    return 0;
}
