# HoloGuard HG-1 firmware

Two processors run the HG-1 radar:

| Processor | Location | Role | Code |
|---|---|---|---|
| AMD Versal AI Edge (XCVE2302) | DSP board | JESD204B capture, holographic MIMO signal processing, tracking, classification, GaN spotlight scheduling, Ethernet API | `dsp/` |
| STM32G474 | DSP board (U7) | GaN power sequencing, I_DQ trim, thermal back-off, built-in test, emission interlock | `mcu/` |

`common/hg1_protocol.h` holds the wire formats both processors share. `sim/` holds the independent scenario generator and the verification harness.

## Signal chain (`dsp/`)

```
ADC cube [48 RX][chirp][sample] (6x AD9083 -> JESD204B -> PL DMA -> LPDDR4)
 1 range FFT, Hann                          PL SSR-FFT / AIE      fft.hpp
 2 Doppler FFT, Hann, zero-pad 2^n          AIE                   signal_processor.cpp
 3 DDMA: fold to 8 sub-bands, TX0 band from the 2 empty bands
 4 holographic beamforming: 24x12 virtual -> 32x16 beams for EVERY range/Doppler cell   AIE-ML
 5 2-D CA-CFAR on the beam-max map, zero-Doppler clutter notch
 6 per detection: coherent DDMA hypothesis test (8 sub-band mappings, full 288-element beam),
   zoom-DFT angle refinement (1/8 beam), range/Doppler interpolation, SNR, RCS,
   RX-beamformed micro-Doppler feature                                                 APU
 7 EKF tracker (CV, 6-state, r/az/el/vr measurements), GNN, M-of-N       tracker.cpp
 8 classifier (rotor micro-Doppler / speed), threat score, GaN spotlight -> ADAR1000 phase words
 9 binary UDP stream (hg1_protocol.h, CRC-32) + JSON lines              app/hg1_radard.cpp
```

On the Versal, stages 1–4 map onto the PL and the AIE-ML array. The C++ here is the bit-accurate reference those kernels are checked against, and it also runs on the APU as the fallback path. Stages 5–9 run on the APU as written.

Two profiles live in `holo::RadarConfig`:

- **`production()`**: 0.6 m bins, 3 km instrumented, 50 ms CPI, 625 chirps.
- **`sim_long_range()`**: same array, carrier, PRF and DDMA plan, but 3 m bins and 128 chirps, so a laptop can replay it.

## Housekeeping MCU (`mcu/`)

Depletion-mode GaN conducts at Vg = 0 V, so `power_seq.c` enforces this sequence:

- **Power-up:** −5 V gate rail → gates to pinch-off → 28 V drain → closed-loop I_DQ trim (50 mA per PA).
- **Power-down:** TX mute → gates to pinch-off → drain off → discharge → −5 V off.

A −5 V comparator (COMP1 → TIM1 break) also opens the drain switch in hardware. The firmware re-checks every invariant every 1 ms.

The emission interlock (`app.c`) only lets the GaN PAs radiate when all of these hold:

- the Versal heartbeat is under 2 s old,
- the PAs are below their thermal trip,
- the RF section is above −40 °C,
- no fault is latched.

Thermal back-off (`thermal.c`) is linear between +60 and +80 °C, up to 3 dB, with a trip at +95 °C.

- `mcu/src/`: portable application (C11)
- `mcu/target/`: STM32Cube HAL BSP plus `main.c`. Not compiled here; build it in STM32CubeIDE. The ADAR1000 register map is flagged `VERIFY`.
- `mcu/sim/`: host hardware model (rails, GaN I_D(V_G) physics, thermal, UART loopback, fault injection)
- `mcu/test/`: 38 checks covering sequencing order, −5 V loss, heartbeat loss, thermal back-off and hysteresis, cold start, shutdown order, COBS/CRC framing

## Build and run (Windows, MSVC 2022)

```bat
build_host.bat
build\test_dsp.exe
build\test_mcu.exe
python sim\gen_scenario.py --frames 24 --period 0.1
build\hg1_radard.exe --input sim\out\scenario.iq --out sim\out
python sim\verify.py
```

On Linux or for Versal (Petalinux SDK), use `cmake -B build && cmake --build build && ctest --test-dir build`.

## Verification results (`sim/results/`)

The scenario is three movers (Phantom-class quad at 560 m, FPV at 360 m inbound at 28 m/s, a gull at 280 m) plus five static clutter objects, TX leakage and thermal noise. The raw ADC data is synthesised independently in Python from the exact array geometry.

| Target | Pd per 10 ms CPI | Range RMSE | Az RMSE | El RMSE | Vr RMSE | Class |
|---|---|---|---|---|---|---|
| FPV (−22 dBsm) | 0.96 | 0.89 m | 0.45° | 0.65° | 0.53 m/s | UAS-rotary ✔ |
| Gull (−19 dBsm) | 0.88 | 0.30 m | 0.13° | 0.22° | 0.07 m/s | bird ✔ |
| Phantom 4 (−17 dBsm, 560 m) | 0.38 | 1.02 m | 0.44° | 0.78° | 0.47 m/s | UAS-rotary ✔ |

- Zero false confirmed tracks; 6 false plots in 24 CPIs.
- The FPV is spotlighted with threat 0.94.
- Host CPU (single thread): about 190 ms per CPI.

The Phantom's low Pd is a property of the short 10 ms simulation CPI. Production uses 50 ms CPIs and a 400 ms window, which is about +9.5 dB.

## Known limitations / next steps

- **DDMA blind speeds.** Targets whose Doppler falls within ±2 bins of a sub-band multiple are notched. In production that is about 10 % of the velocity axis, removed by staggering the PRI between CPIs (80/87 µs).
- **Hovering drones** (vr ≈ 0) are notched with the clutter. Next step is a clutter-map (temporal) CFAR plus detection on rotor micro-Doppler alone.
- **Velocities beyond ±58 m/s** need range-walk (keystone) ambiguity resolution, which isn't implemented yet.
- **AIE-ML/PL kernels** (Vitis HLS + AIE graph) still have to be written against this reference, and on-target timing closure is unproven.
- **The STM32 target BSP** hasn't been compiled or run on hardware.
