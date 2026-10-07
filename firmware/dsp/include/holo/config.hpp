// HoloGuard HG-1 -- radar configuration (mirrors hg1_params.py)
#pragma once
#include <cmath>
#include <complex>
#include <cstdint>
#include <string>
#include <vector>

namespace holo {

using cf32 = std::complex<float>;
constexpr double kC = 299792458.0;
constexpr double kPi = 3.14159265358979323846;

struct Vec2 { double x, y; };            // metres, x = azimuth axis, y = elevation axis (up)

struct RadarConfig {
    // ---- RF / waveform -------------------------------------------------
    double f0_hz = 16.0e9;
    double bw_hz = 250e6;                // chirp bandwidth (surveillance)
    double t_chirp_s = 75e-6;            // active ramp
    double t_pri_s = 80e-6;              // ramp + reset  -> PRF 12.5 kHz
    int n_samples = 8192;                // complex samples per chirp (range FFT size)
    int n_chirps = 625;                  // chirps per CPI (Doppler FFT size, zero-padded to pow2)
    int n_subbands = 8;                  // DDMA: 6 TX + 2 empty bands
    double frame_period_s = 0.050;       // CPI refresh (sliding window step)

    // ---- link budget (RCS estimation; see analysis/system_budget.py) ------
    double pt_w = 6.0;                   // total GaN output, 6 x 1 W
    double g_elem_dbi = 5.0;
    double nf_db = 2.8;
    double loss_db = 4.5;
    double proc_loss_db = 3.6;           // Hann x2 + Taylor taper (already in loss_db budget split)

    // ---- array geometry (metres) ---------------------------------------
    double pitch_m = 9.0e-3;
    std::vector<Vec2> tx;                // 6
    std::vector<Vec2> rx;                // 48

    // ---- processing ------------------------------------------------------
    int az_fft = 32;                     // beam grid (zero-padded 24 -> 32)
    int el_fft = 16;                     // beam grid (zero-padded 12 -> 16)
    int cfar_train_r = 10, cfar_guard_r = 3;
    int cfar_train_d = 3, cfar_guard_d = 1;
    double cfar_alpha_db = 4.6;          // over local mean of the max-of-512-beams statistic (Pfa ~1e-5/cell)
    double clutter_notch_mps = 1.0;      // zero-Doppler notch (static clutter), >= +-2 bins
    int min_range_bin = 6;               // TX/RX leakage + near-field blanking
    double ddma_margin_db = 0.25;        // best vs 2nd-best sub-band hypothesis (coherent beam)
    int max_range_margin = 4;            // anti-alias roll-off / leakage wrap at the top of the IF band

    // ---- derived --------------------------------------------------------
    int n_tx() const { return int(tx.size()); }
    int n_rx() const { return int(rx.size()); }
    double lambda() const { return kC / f0_hz; }
    double fs_hz() const { return n_samples / t_chirp_s; }
    double range_res() const { return kC / (2.0 * bw_hz); }
    double r_max() const { return n_samples * range_res(); }
    int dfft() const { int n = 1; while (n < n_chirps) n <<= 1; return n; }
    int bins_per_subband() const { return dfft() / n_subbands; }
    double vel_res() const { return lambda() / (2.0 * dfft() * t_pri_s); }
    double v_unamb() const { return lambda() / (4.0 * t_pri_s); }

    static RadarConfig hg1_geometry(RadarConfig c) {
        c.tx.clear(); c.rx.clear();
        const double txx[2] = {-54.0, 54.0}, txy[3] = {76.5, 40.5, 4.5};
        for (double y : txy) for (double x : txx) c.tx.push_back({x * 1e-3, y * 1e-3});
        for (int j = 0; j < 4; ++j)
            for (int i = 0; i < 12; ++i)
                c.rx.push_back({(-49.5 + 9.0 * i) * 1e-3, (-49.5 - 9.0 * j) * 1e-3});
        return c;
    }
    // Production surveillance mode (0.6 m bins, 3 km instrumented, 50 ms CPI).
    static RadarConfig production() { return hg1_geometry(RadarConfig{}); }
    // Long-range / simulation profile: 3 m bins, 1.5 km, 128-chirp CPI.
    // Same array, carrier, PRF and DDMA plan -> exercises the identical chain
    // at a data size a laptop can process in real time.
    static RadarConfig sim_long_range() {
        RadarConfig c;
        c.bw_hz = 50e6;
        c.n_samples = 512;
        c.n_chirps = 128;
        c.cfar_train_r = 8;
        return hg1_geometry(c);
    }
};

// Virtual (sum co-array) position of TX k, RX r on the 24 x 12 grid.
struct GridIndex { int ix, iy; };
inline GridIndex virtual_grid(const RadarConfig& c, int k, int r) {
    double vx = c.tx[k].x + c.rx[r].x, vy = c.tx[k].y + c.rx[r].y;
    // min virtual x = -103.5 mm, min y = -72 mm (see antenna/array_design.py)
    int ix = int(std::lround((vx + 103.5e-3) / c.pitch_m));
    int iy = int(std::lround((vy + 72.0e-3) / c.pitch_m));
    return {ix, iy};
}

}  // namespace holo
