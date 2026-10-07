// HoloGuard HG-1 DSP unit tests (host).
#include <cmath>
#include <complex>
#include <cstdio>
#include <set>
#include <vector>

#include "holo/pipeline.hpp"

using namespace holo;
static int g_pass = 0, g_fail = 0;
#define CHECK(c, ...)                                                    \
    do {                                                                 \
        if (c) ++g_pass;                                                 \
        else { ++g_fail; std::printf("  FAIL line %d: ", __LINE__);      \
               std::printf(__VA_ARGS__); std::printf("\n"); }            \
    } while (0)

static void test_fft() {
    std::printf("test_fft\n");
    for (int n : {16, 128, 512}) {
        std::vector<cf32> x(n), y;
        for (int i = 0; i < n; ++i) x[i] = cf32(std::sin(0.3f * i) + 0.1f * i, std::cos(1.1f * i));
        y = x;
        FFT(n).forward(y.data());
        double err = 0;
        for (int k = 0; k < n; ++k) {
            std::complex<double> acc = 0;
            for (int i = 0; i < n; ++i) acc += std::complex<double>(x[i]) * std::polar(1.0, -2 * kPi * k * i / n);
            err = std::max(err, std::abs(acc - std::complex<double>(y[k])) / std::sqrt(double(n)));
        }
        CHECK(err < 1e-3, "FFT %d max err %.2e", n, err);
    }
}

static void test_virtual_array() {
    std::printf("test_virtual_array\n");
    RadarConfig c = RadarConfig::production();
    std::set<std::pair<int, int>> cells;
    int minx = 99, maxx = -1, miny = 99, maxy = -1;
    for (int k = 0; k < c.n_tx(); ++k)
        for (int r = 0; r < c.n_rx(); ++r) {
            GridIndex g = virtual_grid(c, k, r);
            cells.insert({g.ix, g.iy});
            minx = std::min(minx, g.ix); maxx = std::max(maxx, g.ix);
            miny = std::min(miny, g.iy); maxy = std::max(maxy, g.iy);
        }
    CHECK(cells.size() == 288, "288 unique virtual elements (%zu)", cells.size());
    CHECK(minx == 0 && maxx == 23 && miny == 0 && maxy == 11, "filled 24 x 12 grid [%d..%d]x[%d..%d]", minx, maxx,
          miny, maxy);
    CHECK(c.pitch_m / c.lambda() < 0.5 + 1e-3 || c.pitch_m < 3e8 / 16.5e9 / 2 + 1e-4, "pitch <= lambda/2 at f_max");
}

static void test_ddma_shift() {
    std::printf("test_ddma_shift\n");
    RadarConfig c = RadarConfig::sim_long_range();
    const int N = c.dfft();
    for (int k = 0; k < c.n_tx(); ++k) {
        std::vector<cf32> x(N);
        for (int l = 0; l < c.n_chirps; ++l) x[l] = std::polar(1.0f, float(ddma_phase(c, k, l)));
        FFT(N).forward(x.data());
        int pk = 0;
        for (int i = 1; i < N; ++i) if (std::norm(x[i]) > std::norm(x[pk])) pk = i;
        CHECK(pk == k * c.bins_per_subband(), "TX%d code lands in sub-band %d (bin %d)", k, k, pk);
    }
    CHECK(std::fabs(c.v_unamb() - 58.6) < 0.5, "full-PRF unambiguous velocity %.1f m/s", c.v_unamb());
}

static void test_spotlight() {
    std::printf("test_spotlight\n");
    RadarConfig c = RadarConfig::production();
    Track t;
    t.confirmed = true;
    t.cls = TrackClass::UAS_Rotary;
    t.threat = 0.9;
    const double az = 0.35, el = 0.12, r = 1500;
    t.x = {r * std::sin(az) * std::cos(el), r * std::cos(az) * std::cos(el), r * std::sin(el), 0, 0, 0};
    SpotlightCommand s = plan_spotlight(c, {t});
    CHECK(s.active && s.track_id == t.id, "spotlight engaged");
    // coherent sum of the 6 TX fields at the target with the quantised phases
    const double u = std::sin(az) * std::cos(el), v = std::sin(el);
    std::complex<double> acc = 0;
    for (int k = 0; k < 6; ++k) {
        const double geo = 2 * kPi * (c.tx[k].x * u + c.tx[k].y * v) / c.lambda();
        acc += std::polar(1.0, geo + s.phase_code[k] * 2 * kPi / 128.0);
    }
    const double g = 20 * std::log10(std::abs(acc) / std::sqrt(6.0));
    CHECK(g > 7.7, "on-target array gain %.2f dB (ideal 7.78)", g);
}

static void test_tracker() {
    std::printf("test_tracker\n");
    RadarConfig c = RadarConfig::sim_long_range();
    Tracker trk(c);
    double x = 300, y = 900, z = 60, vx = -6, vy = -14, vz = 0.5;
    for (int f = 0; f < 30; ++f) {
        const double t = f * 0.1, px = x + vx * t, py = y + vy * t, pz = z + vz * t;
        const double r = std::sqrt(px * px + py * py + pz * pz);
        Plot p;
        p.range_m = r + 0.5 * std::sin(1.7 * f);
        p.az_rad = std::atan2(px, py) + 0.002 * std::cos(2.3 * f);
        p.el_rad = std::asin(pz / r) + 0.003 * std::sin(1.1 * f);
        p.vr_mps = (px * vx + py * vy + pz * vz) / r;
        p.snr_db = 18;
        p.md_ratio = 0.3;
        p.x = px; p.y = py; p.z = pz;
        trk.update({p}, t);
    }
    CHECK(trk.tracks().size() == 1, "single track (%zu)", trk.tracks().size());
    const Track& tk = trk.tracks()[0];
    const double t = 2.9;
    const double ep = std::hypot(std::hypot(tk.x[0] - (x + vx * t), tk.x[1] - (y + vy * t)), tk.x[2] - (z + vz * t));
    const double ev = std::hypot(std::hypot(tk.x[3] - vx, tk.x[4] - vy), tk.x[5] - vz);
    CHECK(tk.confirmed, "confirmed");
    CHECK(ep < 4.0, "position error %.2f m", ep);
    CHECK(ev < 1.5, "velocity error %.2f m/s", ev);
    CHECK(tk.cls == TrackClass::UAS_Rotary, "classified UAS-rotary (%s)", to_string(tk.cls));
}

int main() {
    test_fft();
    test_virtual_array();
    test_ddma_shift();
    test_spotlight();
    test_tracker();
    std::printf("\n%d checks passed, %d failed\n", g_pass, g_fail);
    return g_fail ? 1 : 0;
}
