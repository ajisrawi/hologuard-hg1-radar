// HoloGuard HG-1 -- 3-D EKF tracker, GNN association, M-of-N track management,
// micro-Doppler classification and GaN spotlight scheduling.
#include <algorithm>
#include <cmath>
#include <limits>

#include "holo/pipeline.hpp"

namespace holo {

namespace {

using Mat6 = std::array<double, 36>;
using Vec4 = std::array<double, 4>;

inline double& at(Mat6& m, int r, int c) { return m[size_t(r) * 6 + c]; }
inline double at(const Mat6& m, int r, int c) { return m[size_t(r) * 6 + c]; }

Vec4 hmeas(const std::array<double, 6>& x) {
    const double r = std::sqrt(x[0] * x[0] + x[1] * x[1] + x[2] * x[2]);
    const double az = std::atan2(x[0], x[1]);
    const double el = std::asin(std::clamp(x[2] / std::max(r, 1e-6), -1.0, 1.0));
    const double vr = (x[0] * x[3] + x[1] * x[4] + x[2] * x[5]) / std::max(r, 1e-6);
    return {r, az, el, vr};
}

// solve 4x4 symmetric positive definite system via Gauss-Jordan inverse
bool inv4(const double S[16], double Si[16]) {
    double a[4][8];
    for (int i = 0; i < 4; ++i)
        for (int j = 0; j < 8; ++j) a[i][j] = j < 4 ? S[i * 4 + j] : (j - 4 == i ? 1.0 : 0.0);
    for (int c = 0; c < 4; ++c) {
        int p = c;
        for (int r = c + 1; r < 4; ++r) if (std::fabs(a[r][c]) > std::fabs(a[p][c])) p = r;
        if (std::fabs(a[p][c]) < 1e-18) return false;
        for (int j = 0; j < 8; ++j) std::swap(a[c][j], a[p][j]);
        const double d = a[c][c];
        for (int j = 0; j < 8; ++j) a[c][j] /= d;
        for (int r = 0; r < 4; ++r)
            if (r != c) {
                const double f = a[r][c];
                for (int j = 0; j < 8; ++j) a[r][j] -= f * a[c][j];
            }
    }
    for (int i = 0; i < 4; ++i)
        for (int j = 0; j < 4; ++j) Si[i * 4 + j] = a[i][j + 4];
    return true;
}

double beamwidth(double lam, int n, double pitch) { return 1.18 * 0.886 * lam / (n * pitch); }

Vec4 meas_sigma(const RadarConfig& c, const Plot& z) {
    const double snr = std::pow(10.0, std::max(z.snr_db, 3.0) / 10.0);
    const double k = 1.0 / (1.6 * std::sqrt(2.0 * snr));
    const double cal = 0.1 * kPi / 180.0;
    const double s_az = std::hypot(beamwidth(c.lambda(), 24, c.pitch_m) * k, cal);
    const double s_el = std::hypot(beamwidth(c.lambda(), 12, c.pitch_m) * k, cal);
    return {std::max(0.25 * c.range_res(), 0.15), s_az, s_el, std::max(0.3 * c.vel_res(), 0.05)};
}

}  // namespace

void Tracker::predict(Track& t, double dt) const {
    // constant-velocity model, white-acceleration process noise
    for (int i = 0; i < 3; ++i) t.x[i] += dt * t.x[i + 3];
    Mat6 F{};
    for (int i = 0; i < 6; ++i) at(F, i, i) = 1.0;
    for (int i = 0; i < 3; ++i) at(F, i, i + 3) = dt;
    Mat6 FP{}, P2{};
    for (int r = 0; r < 6; ++r)
        for (int c = 0; c < 6; ++c) {
            double s = 0;
            for (int k = 0; k < 6; ++k) s += at(F, r, k) * at(t.P, k, c);
            at(FP, r, c) = s;
        }
    for (int r = 0; r < 6; ++r)
        for (int c = 0; c < 6; ++c) {
            double s = 0;
            for (int k = 0; k < 6; ++k) s += at(FP, r, k) * at(F, c, k);
            at(P2, r, c) = s;
        }
    const double q = p_.q_accel * p_.q_accel;
    for (int i = 0; i < 3; ++i) {
        at(P2, i, i) += q * dt * dt * dt * dt / 4.0;
        at(P2, i, i + 3) += q * dt * dt * dt / 2.0;
        at(P2, i + 3, i) += q * dt * dt * dt / 2.0;
        at(P2, i + 3, i + 3) += q * dt * dt;
    }
    t.P = P2;
}

bool Tracker::kalman_update(Track& t, const Plot& z, double* d2_out, bool apply) {
    const Vec4 hz = hmeas(t.x);
    double H[4][6];
    for (int j = 0; j < 6; ++j) {           // numerical Jacobian
        auto xp = t.x;
        const double e = j < 3 ? 1e-3 : 1e-4;
        xp[j] += e;
        const Vec4 hp = hmeas(xp);
        for (int i = 0; i < 4; ++i) H[i][j] = (hp[i] - hz[i]) / e;
    }
    const Vec4 sg = meas_sigma(c_, z);
    double y[4] = {z.range_m - hz[0], z.az_rad - hz[1], z.el_rad - hz[2], z.vr_mps - hz[3]};
    double PHt[6][4];
    for (int r = 0; r < 6; ++r)
        for (int c = 0; c < 4; ++c) {
            double s = 0;
            for (int k = 0; k < 6; ++k) s += at(t.P, r, k) * H[c][k];
            PHt[r][c] = s;
        }
    double S[16], Si[16];
    for (int r = 0; r < 4; ++r)
        for (int c = 0; c < 4; ++c) {
            double s = 0;
            for (int k = 0; k < 6; ++k) s += H[r][k] * PHt[k][c];
            S[r * 4 + c] = s + (r == c ? sg[r] * sg[r] : 0.0);
        }
    if (!inv4(S, Si)) return false;
    double d2 = 0;
    for (int r = 0; r < 4; ++r)
        for (int c = 0; c < 4; ++c) d2 += y[r] * Si[r * 4 + c] * y[c];
    if (d2_out) *d2_out = d2;
    if (!apply) return true;
    double K[6][4];
    for (int r = 0; r < 6; ++r)
        for (int c = 0; c < 4; ++c) {
            double s = 0;
            for (int k = 0; k < 4; ++k) s += PHt[r][k] * Si[k * 4 + c];
            K[r][c] = s;
        }
    for (int r = 0; r < 6; ++r)
        for (int c = 0; c < 4; ++c) t.x[r] += K[r][c] * y[c];
    Mat6 Pn = t.P;                           // P = (I - K H) P
    for (int r = 0; r < 6; ++r)
        for (int c = 0; c < 6; ++c) {
            double s = 0;
            for (int k = 0; k < 4; ++k) s += K[r][k] * PHt[c][k];
            at(Pn, r, c) -= s;
        }
    t.P = Pn;
    return true;
}

void Tracker::classify(Track& t) const {
    const double speed = std::sqrt(t.x[3] * t.x[3] + t.x[4] * t.x[4] + t.x[5] * t.x[5]);
    if (t.md_n < 4) { t.cls = TrackClass::Unknown; }
    else if (t.md_avg > p_.md_rotor_threshold) t.cls = TrackClass::UAS_Rotary;
    else if (speed > 22.0) t.cls = TrackClass::UAS_FixedWing;
    else if (speed < 0.8) t.cls = TrackClass::Ground;
    else t.cls = TrackClass::Bird;

    const double r = std::sqrt(t.x[0] * t.x[0] + t.x[1] * t.x[1] + t.x[2] * t.x[2]);
    const double closing = -(t.x[0] * t.x[3] + t.x[1] * t.x[4] + t.x[2] * t.x[5]) / std::max(r, 1.0);
    double base = 0.0;
    if (t.cls == TrackClass::UAS_Rotary || t.cls == TrackClass::UAS_FixedWing) base = 0.6;
    else if (t.cls == TrackClass::Unknown) base = 0.3;
    double tti = closing > 0.5 ? r / closing : 1e9;    // time to intercept the site
    t.threat = std::clamp(base + 0.4 * std::exp(-tti / 60.0), 0.0, 1.0) * (t.confirmed ? 1.0 : 0.5);
}

void Tracker::update(const std::vector<Plot>& plots, double t_s) {
    const double dt = t_last_ < 0 ? 0.0 : t_s - t_last_;
    t_last_ = t_s;
    for (auto& t : tracks_) { predict(t, dt); ++t.age; }

    // ---- global-nearest-neighbour (greedy on gated Mahalanobis distance)
    struct Pair { double d2; size_t ti, pi; };
    std::vector<Pair> pairs;
    for (size_t ti = 0; ti < tracks_.size(); ++ti)
        for (size_t pi = 0; pi < plots.size(); ++pi) {
            double d2;
            if (kalman_update(tracks_[ti], plots[pi], &d2, false) && d2 < p_.gate_chi2)
                pairs.push_back({d2, ti, pi});
        }
    std::sort(pairs.begin(), pairs.end(), [](const Pair& a, const Pair& b) { return a.d2 < b.d2; });
    std::vector<char> t_used(tracks_.size(), 0), p_used(plots.size(), 0);
    for (const auto& pr : pairs) {
        if (t_used[pr.ti] || p_used[pr.pi]) continue;
        t_used[pr.ti] = p_used[pr.pi] = 1;
        Track& t = tracks_[pr.ti];
        const Plot& z = plots[pr.pi];
        kalman_update(t, z, nullptr, true);
        ++t.hits;
        t.misses = 0;
        t.snr_last = z.snr_db;
        t.rcs_avg = t.hits == 1 ? z.rcs_dbsm : 0.85 * t.rcs_avg + 0.15 * z.rcs_dbsm;
        if (z.snr_db > 8.0) {
            t.md_avg = t.md_n == 0 ? z.md_ratio : 0.8 * t.md_avg + 0.2 * z.md_ratio;
            ++t.md_n;
        }
        t.hist.push_back(1);
    }
    for (size_t ti = 0; ti < tracks_.size(); ++ti)
        if (!t_used[ti]) { ++tracks_[ti].misses; tracks_[ti].hist.push_back(0); }

    // ---- track management
    for (auto& t : tracks_) {
        if (t.hist.size() > size_t(p_.confirm_n)) t.hist.erase(t.hist.begin());
        int m = 0;
        for (int h : t.hist) m += h;
        if (!t.confirmed && m >= p_.confirm_m) t.confirmed = true;
        classify(t);
    }
    tracks_.erase(std::remove_if(tracks_.begin(), tracks_.end(), [&](const Track& t) {
        return t.misses > (t.confirmed ? p_.delete_misses_confirmed : p_.delete_misses_tentative);
    }), tracks_.end());

    // ---- initiate tentative tracks from unassociated plots
    for (size_t pi = 0; pi < plots.size(); ++pi) {
        if (p_used[pi]) continue;
        const Plot& z = plots[pi];
        Track t;
        t.id = next_id_++;
        const double r = std::max(z.range_m, 1.0);
        const double ux = z.x / r, uy = z.y / r, uz = z.z / r;
        t.x = {z.x, z.y, z.z, z.vr_mps * ux, z.vr_mps * uy, z.vr_mps * uz};
        const Vec4 sg = meas_sigma(c_, z);
        const double sp = std::max(sg[0], r * std::max(sg[1], sg[2]));
        t.P.fill(0.0);
        for (int i = 0; i < 3; ++i) { at(t.P, i, i) = sp * sp; at(t.P, i + 3, i + 3) = 15.0 * 15.0; }
        t.hits = 1;
        t.hist = {1};
        t.snr_last = z.snr_db;
        t.rcs_avg = z.rcs_dbsm;
        if (z.snr_db > 8.0) { t.md_avg = z.md_ratio; t.md_n = 1; }
        tracks_.push_back(t);
    }
}

SpotlightCommand plan_spotlight(const RadarConfig& c, const std::vector<Track>& tracks) {
    SpotlightCommand cmd;
    const Track* best = nullptr;
    for (const auto& t : tracks)
        if (t.confirmed && (t.cls == TrackClass::UAS_Rotary || t.cls == TrackClass::UAS_FixedWing) &&
            (!best || t.threat > best->threat))
            best = &t;
    if (!best) return cmd;
    const double r = std::sqrt(best->x[0] * best->x[0] + best->x[1] * best->x[1] + best->x[2] * best->x[2]);
    const double u = best->x[0] / r, v = best->x[2] / r;      // direction cosines (az, el axes)
    cmd.active = true;
    cmd.track_id = best->id;
    cmd.az_rad = std::atan2(best->x[0], best->x[1]);
    cmd.el_rad = std::asin(v);
    cmd.gain_db = 10.0 * std::log10(double(c.n_tx()));
    for (int k = 0; k < c.n_tx(); ++k) {
        double ph = -2.0 * kPi * (c.tx[k].x * u + c.tx[k].y * v) / c.lambda();
        ph = std::fmod(ph, 2.0 * kPi);
        if (ph < 0) ph += 2.0 * kPi;
        cmd.phase_code[k] = uint8_t(std::lround(ph / (2.0 * kPi / 128.0)) % 128);   // 7-bit, 2.8125 deg
    }
    return cmd;
}

}  // namespace holo
