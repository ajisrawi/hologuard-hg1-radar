// HoloGuard HG-1 -- holographic (staring) MIMO signal-processing chain.
//
//   ADC cube [rx][chirp][sample]  (JESD204B -> PL DMA -> DDR)
//     1. range FFT  (Hann)                         PL / AIE
//     2. Doppler FFT (Hann, zero-pad to 2^n)       AIE
//     3. DDMA demux: fold Doppler into the 8 sub-bands, find TX0 band from
//        the 2 empty bands -> unambiguous Doppler over the full PRF
//     4. holographic beamforming: 24 x 12 virtual array -> 32 x 16 beams for
//        EVERY range/Doppler cell (coherent, pre-detection)    AIE-ML
//     5. 2-D CA-CFAR on the beam-max map, zero-Doppler clutter notch
//     6. plot extraction: range / Doppler / az / el interpolation, SNR,
//        micro-Doppler feature                                 APU
//   plots -> Tracker (EKF, GNN, M/N) -> classifier -> spotlight scheduler
#pragma once
#include <array>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

#include "config.hpp"
#include "fft.hpp"

namespace holo {

struct Plot {
    double range_m = 0, vr_mps = 0, az_rad = 0, el_rad = 0;
    double snr_db = 0, rcs_dbsm = 0;
    double x = 0, y = 0, z = 0;          // radar frame: x right, y boresight, z up
    double md_ratio = 0;                 // micro-Doppler off-line / body energy
    int rbin = 0, dbin = 0;
};

enum class TrackClass : uint8_t { Unknown = 0, UAS_Rotary = 1, UAS_FixedWing = 2, Bird = 3, Ground = 4 };
const char* to_string(TrackClass c);

struct Track {
    uint32_t id = 0;
    bool confirmed = false;
    int hits = 0, misses = 0, age = 0;
    std::array<double, 6> x{};           // x y z vx vy vz
    std::array<double, 36> P{};          // covariance (row-major 6x6)
    double md_avg = 0, rcs_avg = -30, snr_last = 0;
    int md_n = 0;
    TrackClass cls = TrackClass::Unknown;
    double threat = 0;                   // 0..1 for spotlight scheduling
    std::vector<int> hist;               // M-of-N history (1 = hit)
};

struct CpiResult {
    std::vector<Plot> plots;
    double noise_floor_db = 0;
    int cells_tested = 0, cfar_hits = 0, ddma_rejects = 0;
    double proc_ms = 0;
};

class SignalProcessor {
public:
    explicit SignalProcessor(const RadarConfig& cfg);
    // iq: int16 interleaved I/Q, layout [rx][chirp][sample][2]
    CpiResult process(const int16_t* iq, double adc_lsb_v = 1.0);
    // per virtual channel complex calibration (OTA probe), default unity
    void set_calibration(const std::vector<cf32>& cal) { cal_ = cal; }
    const RadarConfig& cfg() const { return c_; }

private:
    void range_doppler(const int16_t* iq);
    void build_power_map();
    int resolve_tx0_band(int rbin, int dmod) const;
    float beamform_cell(int rbin, int d, int* best_az, int* best_el, std::vector<float>* map);
    void cfar(std::vector<char>& hit, std::vector<float>& thr) const;
    Plot extract(int rbin, int dmod, int m) ;

    RadarConfig c_;
    int ns_, nd_, nb_, nrx_, ntx_, nsub_;
    FFT fft_r_, fft_d_, fft_az_, fft_el_;
    std::vector<float> win_r_, win_d_, tap_;    // tap_: virtual-aperture taper per (tx,rx)
    std::vector<GridIndex> grid_;
    std::vector<cf32> cube_;                    // [rx][nd][ns]
    std::vector<float> pmap_;                   // [ns][nd]  non-coherent RX sum
    std::vector<float> bmax_;                   // [ns][nb]  beam-max (holographic) map
    std::vector<int16_t> bidx_;                 // [ns][nb]  best beam index az*el_fft+el
    std::vector<int8_t> band_;                  // [ns][nb]  resolved TX0 band m
    std::vector<cf32> cal_;
    std::vector<cf32> beam_;                    // scratch az_fft x el_fft
    double noise_bin_ = 1.0;
};

struct TrackerParams {
    double q_accel = 6.0;        // m/s^2 process noise (manoeuvring sUAS)
    double gate_chi2 = 16.3;     // 4-dof, ~99.7 %
    int confirm_m = 3, confirm_n = 5;
    int delete_misses_tentative = 4, delete_misses_confirmed = 10;
    double md_rotor_threshold = 0.08;
};

class Tracker {
public:
    explicit Tracker(const RadarConfig& cfg, TrackerParams p = {}) : c_(cfg), p_(p) {}
    void update(const std::vector<Plot>& plots, double t_s);
    const std::vector<Track>& tracks() const { return tracks_; }

private:
    void predict(Track& t, double dt) const;
    bool kalman_update(Track& t, const Plot& z, double* d2_out, bool apply);
    void classify(Track& t) const;
    RadarConfig c_;
    TrackerParams p_;
    std::vector<Track> tracks_;
    uint32_t next_id_ = 1;
    double t_last_ = -1;
};

// GaN "spotlight": coherent 6-TX beam on the highest-threat confirmed track.
struct SpotlightCommand {
    bool active = false;
    uint32_t track_id = 0;
    double az_rad = 0, el_rad = 0, gain_db = 0;
    std::array<uint8_t, 6> phase_code{};   // ADAR1000 phase word, 2.8125 deg LSB
};
SpotlightCommand plan_spotlight(const RadarConfig& c, const std::vector<Track>& tracks);

// DDMA slow-time phase code for TX k, chirp l (radians) -- programmed into
// the ADAR1000 beam-state memory and stepped by the chirp trigger.
inline double ddma_phase(const RadarConfig& c, int k, int l) {
    return 2.0 * kPi * double(k) * double(l) / double(c.n_subbands);
}

}  // namespace holo
