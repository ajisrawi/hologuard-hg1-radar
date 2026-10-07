// HoloGuard HG-1 -- holographic MIMO signal processor (reference implementation).
#define _CRT_SECURE_NO_WARNINGS   // std::getenv for the HG1_DEBUG_BANDS trace
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <numeric>

#include "holo/pipeline.hpp"

namespace holo {

const char* to_string(TrackClass c) {
    switch (c) {
        case TrackClass::UAS_Rotary: return "UAS-rotary";
        case TrackClass::UAS_FixedWing: return "UAS-fixed-wing";
        case TrackClass::Bird: return "bird";
        case TrackClass::Ground: return "ground";
        default: return "unknown";
    }
}

SignalProcessor::SignalProcessor(const RadarConfig& cfg)
    : c_(cfg),
      ns_(cfg.n_samples), nd_(cfg.dfft()), nb_(cfg.bins_per_subband()),
      nrx_(cfg.n_rx()), ntx_(cfg.n_tx()), nsub_(cfg.n_subbands),
      fft_r_(cfg.n_samples), fft_d_(cfg.dfft()), fft_az_(cfg.az_fft), fft_el_(cfg.el_fft) {
    win_r_ = hann(ns_);
    win_d_ = hann(c_.n_chirps);
    // Taylor taper over the 24 x 12 virtual aperture (-35 dB az / -30 dB el)
    auto tx_ = taylor(24, 4, 35.0), ty_ = taylor(12, 4, 30.0);
    grid_.resize(size_t(ntx_) * nrx_);
    tap_.resize(grid_.size());
    for (int k = 0; k < ntx_; ++k)
        for (int r = 0; r < nrx_; ++r) {
            GridIndex g = virtual_grid(c_, k, r);
            grid_[size_t(k) * nrx_ + r] = g;
            tap_[size_t(k) * nrx_ + r] = tx_[g.ix] * ty_[g.iy];
        }
    cal_.assign(grid_.size(), cf32(1.0f, 0.0f));
    cube_.assign(size_t(nrx_) * nd_ * ns_, cf32{});
    pmap_.assign(size_t(ns_) * nd_, 0.0f);
    bmax_.assign(size_t(ns_) * nb_, 0.0f);
    bidx_.assign(size_t(ns_) * nb_, 0);
    band_.assign(size_t(ns_) * nb_, 0);
    beam_.assign(size_t(c_.az_fft) * c_.el_fft, cf32{});
}

// --------------------------------------------------------------- 1 + 2
void SignalProcessor::range_doppler(const int16_t* iq) {
    const int nl = c_.n_chirps;
    for (int r = 0; r < nrx_; ++r) {
        cf32* cr = &cube_[size_t(r) * nd_ * ns_];
        for (int l = 0; l < nd_; ++l) {
            cf32* row = cr + size_t(l) * ns_;
            if (l >= nl) {
                std::fill(row, row + ns_, cf32{});
                continue;
            }
            const int16_t* src = iq + (size_t(r) * nl + l) * ns_ * 2;
            const float wd = win_d_[l];
            for (int s = 0; s < ns_; ++s)
                row[s] = cf32(src[2 * s], src[2 * s + 1]) * (win_r_[s] * wd);
            fft_r_.forward(row);
        }
        for (int s = 0; s < ns_; ++s) fft_d_.forward(cr + s, ns_);   // slow-time, strided
    }
}

void SignalProcessor::build_power_map() {
    std::fill(pmap_.begin(), pmap_.end(), 0.0f);
    for (int r = 0; r < nrx_; ++r) {
        const cf32* cr = &cube_[size_t(r) * nd_ * ns_];
        for (int d = 0; d < nd_; ++d)
            for (int s = 0; s < ns_; ++s) pmap_[size_t(s) * nd_ + d] += std::norm(cr[size_t(d) * ns_ + s]);
    }
    // robust noise-per-bin estimate (median of chi^2_{2N} ~ mean)
    std::vector<float> tmp(pmap_.begin() + size_t(c_.min_range_bin) * nd_, pmap_.end());
    std::nth_element(tmp.begin(), tmp.begin() + tmp.size() / 2, tmp.end());
    noise_bin_ = std::max(1e-12, double(tmp[tmp.size() / 2]) / (1.0 - 1.0 / (3.0 * nrx_)));
}

// ----------------------------------------------------------------- 3
// TX k sits in sub-band (m + k) mod 8; bands m+6, m+7 are empty.
int SignalProcessor::resolve_tx0_band(int s, int dmod) const {
    const float* p = &pmap_[size_t(s) * nd_];
    float e[16];
    for (int b = 0; b < nsub_; ++b) e[b] = p[dmod + nb_ * b];
    int best = 0;
    float bestv = 1e30f;
    for (int m = 0; m < nsub_; ++m) {
        float empty = 0.0f;
        for (int b = ntx_; b < nsub_; ++b) empty += e[(m + b) % nsub_];
        if (empty < bestv) { bestv = empty; best = m; }
    }
    return best;
}

// ----------------------------------------------------------------- 4
float SignalProcessor::beamform_cell(int s, int d, int* best_az, int* best_el, std::vector<float>* map) {
    const int A = c_.az_fft, E = c_.el_fft;
    std::fill(beam_.begin(), beam_.end(), cf32{});
    for (int k = 0; k < ntx_; ++k) {
        const int dk = (d + nb_ * k) % nd_;
        for (int r = 0; r < nrx_; ++r) {
            const size_t v = size_t(k) * nrx_ + r;
            const GridIndex g = grid_[v];
            beam_[size_t(g.ix) * E + g.iy] = cube_[(size_t(r) * nd_ + dk) * ns_ + s] * cal_[v] * tap_[v];
        }
    }
    for (int ix = 0; ix < 24; ++ix) fft_el_.forward(&beam_[size_t(ix) * E]);   // rows >= 24 are zero
    for (int iy = 0; iy < E; ++iy) fft_az_.forward(&beam_[iy], E);
    float best = -1.0f;
    for (int ia = 0; ia < A; ++ia)
        for (int ie = 0; ie < E; ++ie) {
            float pw = std::norm(beam_[size_t(ia) * E + ie]);
            if (map) (*map)[size_t(ia) * E + ie] = pw;
            if (pw > best) { best = pw; *best_az = ia; *best_el = ie; }
        }
    return best;
}

// ----------------------------------------------------------------- 5
void SignalProcessor::cfar(std::vector<char>& hit, std::vector<float>& thr) const {
    const double alpha = std::pow(10.0, c_.cfar_alpha_db / 10.0);
    hit.assign(bmax_.size(), 0);
    thr.assign(bmax_.size(), 0.0f);
    for (int s = c_.min_range_bin; s < ns_; ++s) {
        for (int dm = 0; dm < nb_; ++dm) {
            const float cut = bmax_[size_t(s) * nb_ + dm];
            if (cut <= 0.0f) continue;
            double acc = 0.0;
            int n = 0;
            for (int o = c_.cfar_guard_r + 1; o <= c_.cfar_guard_r + c_.cfar_train_r; ++o)
                for (int sg : {-1, 1}) {
                    int ss = s + sg * o;
                    if (ss < c_.min_range_bin || ss >= ns_) continue;
                    float v = bmax_[size_t(ss) * nb_ + dm];
                    if (v > 0.0f) { acc += v; ++n; }
                }
            for (int o = c_.cfar_guard_d + 1; o <= c_.cfar_guard_d + c_.cfar_train_d; ++o)
                for (int sg : {-1, 1}) {
                    int dd = ((dm + sg * o) % nb_ + nb_) % nb_;
                    float v = bmax_[size_t(s) * nb_ + dd];
                    if (v > 0.0f) { acc += v; ++n; }
                }
            if (n < 4) continue;
            const float t = float(alpha * acc / n);
            thr[size_t(s) * nb_ + dm] = t;
            if (cut <= t) continue;
            bool peak = true;   // 3x3 local maximum (Doppler cyclic)
            for (int a = -1; a <= 1 && peak; ++a)
                for (int b = -1; b <= 1; ++b) {
                    if (!a && !b) continue;
                    int ss = s + a, dd = ((dm + b) % nb_ + nb_) % nb_;
                    if (ss < 0 || ss >= ns_) continue;
                    if (bmax_[size_t(ss) * nb_ + dd] > cut) { peak = false; break; }
                }
            hit[size_t(s) * nb_ + dm] = peak;
        }
    }
}

// ----------------------------------------------------------------- 6
static double parabolic(double ym1, double y0, double yp1) {
    double den = ym1 - 2.0 * y0 + yp1;
    if (std::fabs(den) < 1e-12) return 0.0;
    return std::clamp(0.5 * (ym1 - yp1) / den, -0.5, 0.5);
}

Plot SignalProcessor::extract(int s, int dm, int m) {
    const int A = c_.az_fft, E = c_.el_fft;
    const int d = dm + nb_ * m;
    std::vector<float> map(size_t(A) * E);
    int ia = 0, ie = 0;
    const float pk = beamform_cell(s, d, &ia, &ie, &map);
    auto L = [&](int a, int e) {
        a = (a % A + A) % A; e = (e % E + E) % E;
        return std::log(double(map[size_t(a) * E + e]) + 1e-30);
    };
    double fa = ia, fe = ie;
    if (fa >= A / 2.0) fa -= A;
    if (fe >= E / 2.0) fe -= E;
    const double lam = c_.lambda();
    const double du = lam / (A * c_.pitch_m), dv = lam / (E * c_.pitch_m);
    double u = -fa * du, v = -fe * dv;
    {   // zoom: direct DFT on a 1/8-bin local grid around the coarse beam, then parabolic
        std::vector<cf32> sv(grid_.size());
        for (int k = 0; k < ntx_; ++k) {
            const int dk = (d + nb_ * k) % nd_;
            for (int r = 0; r < nrx_; ++r) {
                const size_t vi = size_t(k) * nrx_ + r;
                sv[vi] = cube_[(size_t(r) * nd_ + dk) * ns_ + s] * cal_[vi] * tap_[vi];
            }
        }
        const int Z = 8, H = 8;      // +-1 coarse bin in 1/8 steps
        double best = -1.0;
        int bi = 0, bj = 0;
        std::vector<double> fine(size_t(2 * H + 1) * (2 * H + 1));
        for (int i = -H; i <= H; ++i)
            for (int j = -H; j <= H; ++j) {
                const double uu = u + i * du / Z, vv = v + j * dv / Z;
                std::complex<double> acc = 0.0;
                for (size_t vi = 0; vi < sv.size(); ++vi) {
                    const double ph = 2.0 * kPi * (grid_[vi].ix * c_.pitch_m * uu + grid_[vi].iy * c_.pitch_m * vv) / lam;
                    acc += std::complex<double>(sv[vi]) * std::polar(1.0, ph);
                }
                const double pw = std::norm(acc);
                fine[size_t(i + H) * (2 * H + 1) + (j + H)] = pw;
                if (pw > best) { best = pw; bi = i; bj = j; }
            }
        auto F = [&](int i, int j) {
            i = std::clamp(i, -H, H); j = std::clamp(j, -H, H);
            return std::log(fine[size_t(i + H) * (2 * H + 1) + (j + H)] + 1e-30);
        };
        const double oi = bi + parabolic(F(bi - 1, bj), F(bi, bj), F(bi + 1, bj));
        const double oj = bj + parabolic(F(bi, bj - 1), F(bi, bj), F(bi, bj + 1));
        u += oi * du / Z;
        v += oj * dv / Z;
    }
    (void)L;
    v = std::clamp(v, -0.999, 0.999);
    Plot p;
    p.el_rad = std::asin(v);
    p.az_rad = std::asin(std::clamp(u / std::cos(p.el_rad), -0.999, 0.999));

    auto P = [&](int ss, int dd) {
        ss = std::clamp(ss, 0, ns_ - 1); dd = (dd % nd_ + nd_) % nd_;
        return std::log(double(pmap_[size_t(ss) * nd_ + dd]) + 1e-30);
    };
    const double fr = s + parabolic(P(s - 1, d), P(s, d), P(s + 1, d));
    double fd = d + parabolic(P(s, d - 1), P(s, d), P(s, d + 1));
    if (fd >= nd_ / 2.0) fd -= nd_;
    p.range_m = fr * c_.range_res();
    p.vr_mps = fd * c_.vel_res();
    p.rbin = s;
    p.dbin = d;

    // SNR in the beam domain: noise per virtual channel per bin = noise_bin/nrx
    double w2 = 0.0;
    for (float w : tap_) w2 += double(w) * w;
    const double noise_beam = noise_bin_ / nrx_ * w2;
    p.snr_db = 10.0 * std::log10(std::max(1e-9, (pk - noise_beam) / noise_beam));

    // radar-equation RCS estimate (calibrated against the link budget)
    const double R = std::max(p.range_m, 1.0);
    const double lam2 = lam * lam, k_t0 = 1.380649e-23 * 290.0;
    const double t_cpi = c_.n_chirps * c_.t_pri_s;
    const double g = std::pow(10.0, c_.g_elem_dbi / 10.0);
    const double snr1 = c_.pt_w * g * g * nrx_ * lam2 * t_cpi /
                        (std::pow(4.0 * kPi, 3) * std::pow(R, 4) * k_t0 * std::pow(10.0, c_.nf_db / 10.0) *
                         std::pow(10.0, c_.loss_db / 10.0));
    p.rcs_dbsm = p.snr_db - 10.0 * std::log10(snr1) + c_.proc_loss_db;

    // micro-Doppler: RX-only beam steered at the plot (rejects other-angle
    // energy in the same range bin), unfolded Doppler spectrum; energy
    // outside the 6 body lines and the zero-Doppler lines, normalised by body
    // energy (rotor blades spread over the whole PRF, wings stay near body).
    std::vector<float> rowv(nd_, 0.0f);
    {
        std::vector<cf32> w(nrx_);
        for (int r = 0; r < nrx_; ++r)
            w[r] = std::polar(1.0f, float(2.0 * kPi * (c_.rx[r].x * u + c_.rx[r].y * v) / lam));
        for (int dd = 0; dd < nd_; ++dd) {
            cf32 acc{};
            for (int r = 0; r < nrx_; ++r) acc += w[r] * cube_[(size_t(r) * nd_ + dd) * ns_ + s];
            rowv[dd] = std::norm(acc);
        }
    }
    const float* row = rowv.data();
    std::vector<char> mask(nd_, 0);
    for (int k = 0; k < nsub_; ++k)
        for (int q = -2; q <= 2; ++q) mask[((nb_ * k + q) % nd_ + nd_) % nd_] = 2;   // clutter lines
    for (int k = 0; k < ntx_; ++k)
        for (int q = -2; q <= 2; ++q) mask[((d + nb_ * k + q) % nd_ + nd_) % nd_] = 1;   // body lines win
    double body = 0, off = 0;
    int noff = 0, nbody = 0;
    for (int i = 0; i < nd_; ++i) {
        if (mask[i] == 1) { body += row[i]; ++nbody; }
        else if (mask[i] == 0) { off += row[i]; ++noff; }
    }
    off = std::max(0.0, off - noff * noise_bin_);
    body = std::max(body - nbody * noise_bin_, nbody * noise_bin_);
    p.md_ratio = off / body;

    const double ce = std::cos(p.el_rad);
    p.x = p.range_m * std::sin(p.az_rad) * ce;
    p.y = p.range_m * std::cos(p.az_rad) * ce;
    p.z = p.range_m * std::sin(p.el_rad);
    return p;
}

CpiResult SignalProcessor::process(const int16_t* iq, double) {
    auto t0 = std::chrono::steady_clock::now();
    CpiResult out;
    range_doppler(iq);
    build_power_map();

    std::fill(bmax_.begin(), bmax_.end(), 0.0f);
    // Hann main lobe spans +-2 Doppler bins: notch at least that wide
    const int notch_bins = std::max(2, int(std::ceil(c_.clutter_notch_mps / c_.vel_res())));
    for (int s = c_.min_range_bin; s < ns_ - c_.max_range_margin; ++s) {
        for (int dm = 0; dm < nb_; ++dm) {
            const int m = resolve_tx0_band(s, dm);
            int d = dm + nb_ * m;
            int ds = d >= nd_ / 2 ? d - nd_ : d;
            const size_t ci = size_t(s) * nb_ + dm;
            band_[ci] = int8_t(m);
            if (std::abs(ds) <= notch_bins) continue;
            int ia = 0, ie = 0;
            bmax_[ci] = beamform_cell(s, d, &ia, &ie, nullptr);
            bidx_[ci] = int16_t(ia * c_.el_fft + ie);
            ++out.cells_tested;
        }
    }
    std::vector<char> hit;
    std::vector<float> thr;
    cfar(hit, thr);
    for (int s = 0; s < ns_; ++s)
        for (int dm = 0; dm < nb_; ++dm)
            if (hit[size_t(s) * nb_ + dm]) {
                ++out.cfar_hits;
                // DDMA hypothesis test with the full coherent array: only the
                // correct TX<->sub-band mapping forms a 288-element beam.
                float best = -1.0f, second = -1.0f;
                int mbest = 0, ia = 0, ie = 0;
                for (int m = 0; m < nsub_; ++m) {
                    const float pw = beamform_cell(s, dm + nb_ * m, &ia, &ie, nullptr);
                    if (pw > best) { second = best; best = pw; mbest = m; }
                    else if (pw > second) second = pw;
                }
                const int d = dm + nb_ * mbest;
                const int ds = d >= nd_ / 2 ? d - nd_ : d;
                const double margin_db = 10.0 * std::log10(best / std::max(second, 1e-30f));
                if (std::getenv("HG1_DEBUG_BANDS"))
                    std::fprintf(stderr, "det s=%d dm=%d m_pmap=%d m_beam=%d ds=%d margin=%.1f dB\n", s, dm,
                                 int(band_[size_t(s) * nb_ + dm]), mbest, ds, margin_db);
                if (std::abs(ds) <= notch_bins || margin_db < c_.ddma_margin_db) {
                    ++out.ddma_rejects;
                    continue;
                }
                out.plots.push_back(extract(s, dm, mbest));
            }
    out.noise_floor_db = 10.0 * std::log10(noise_bin_);
    out.proc_ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
    return out;
}

}  // namespace holo
