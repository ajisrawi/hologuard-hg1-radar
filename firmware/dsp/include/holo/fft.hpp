// Radix-2 FFT and windows. On the Versal these map to the AIE-ML FFT
// kernels (Vitis DSP library) / PL SSR FFT; this portable version is the
// bit-for-bit reference for the APU and the host test bench.
#pragma once
#include <cmath>
#include <complex>
#include <vector>

#include "config.hpp"

namespace holo {

class FFT {
public:
    explicit FFT(int n) : n_(n), tw_(n / 2), rev_(n) {
        int lg = 0;
        while ((1 << lg) < n) ++lg;
        for (int i = 0; i < n; ++i) {
            int r = 0;
            for (int b = 0; b < lg; ++b) r |= ((i >> b) & 1) << (lg - 1 - b);
            rev_[i] = r;
        }
        for (int i = 0; i < n / 2; ++i)
            tw_[i] = std::polar(1.0f, float(-2.0 * kPi * i / n));
    }
    int size() const { return n_; }

    // in-place forward transform of n contiguous samples with given stride
    void forward(cf32* x, int stride = 1) const {
        for (int i = 0; i < n_; ++i) {
            int j = rev_[i];
            if (j > i) std::swap(x[i * stride], x[j * stride]);
        }
        for (int len = 2; len <= n_; len <<= 1) {
            int half = len >> 1, step = n_ / len;
            for (int i = 0; i < n_; i += len) {
                for (int k = 0; k < half; ++k) {
                    cf32 w = tw_[k * step];
                    cf32& a = x[(i + k) * stride];
                    cf32& b = x[(i + k + half) * stride];
                    cf32 t = w * b;
                    b = a - t;
                    a = a + t;
                }
            }
        }
    }

private:
    int n_;
    std::vector<cf32> tw_;
    std::vector<int> rev_;
};

inline std::vector<float> hann(int n) {
    std::vector<float> w(n);
    for (int i = 0; i < n; ++i) w[i] = float(0.5 - 0.5 * std::cos(2.0 * kPi * (i + 0.5) / n));
    return w;
}

// Taylor window (nbar, sidelobe level in dB) -- used on the virtual aperture.
inline std::vector<float> taylor(int n, int nbar, double sll_db) {
    double A = std::acosh(std::pow(10.0, sll_db / 20.0)) / kPi;
    double s2 = nbar * nbar / (A * A + (nbar - 0.5) * (nbar - 0.5));
    std::vector<double> Fm(nbar, 0.0);
    for (int m = 1; m < nbar; ++m) {
        double num = 1.0, den = 1.0;
        for (int i = 1; i < nbar; ++i) {
            num *= 1.0 - (double(m) * m / s2) / (A * A + (i - 0.5) * (i - 0.5));
            if (i != m) den *= 1.0 - double(m) * m / (double(i) * i);
        }
        Fm[m] = ((m % 2) ? 1.0 : -1.0) * num / (2.0 * den);
    }
    std::vector<float> w(n);
    double mx = 0.0;
    for (int k = 0; k < n; ++k) {
        double x = (k - (n - 1) / 2.0) / n, v = 1.0;
        for (int m = 1; m < nbar; ++m) v += 2.0 * Fm[m] * std::cos(2.0 * kPi * m * x);
        w[k] = float(v);
        mx = std::max(mx, v);
    }
    for (auto& v : w) v = float(v / mx);
    return w;
}

}  // namespace holo
