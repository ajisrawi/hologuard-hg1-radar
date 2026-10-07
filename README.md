# HoloGuard HG-1: Ku-band GaN 4D holographic counter-UAS radar

A staring (holographic) 6 TX × 48 RX MIMO radar in the **same 163 × 203 × 57 mm envelope as the Echodyne EchoGuard**. It's lighter (1.01 kg vs 1.25 kg), uses less power (46.8 W vs 50 W), has longer range (Phantom 4: 1.5 km detect / 2.3 km spotlight track vs > 1 km) and better 3D accuracy (0.2° / 0.35° at 1 km vs 1° / 1.5°). Every beam is formed digitally from a 288-element virtual array, every CPI.

![hero](render/HG1_hero.png)

| Step | Documents | Sources / outputs |
|---|---|---|
| 1. High-level design | [docs/01_System_Design.md](docs/01_System_Design.md) | `hg1_params.py` (single source of truth), `analysis/` (link budget, trade study, figures) |
| 2. Board design | [docs/03_Board_Design.md](docs/03_Board_Design.md) | `board/generate_boards.py` → `board/kicad/*.kicad_pcb` (0 DRC errors), renders, STEP/GLB, `BOM_HG1.csv` |
| 3. Antenna design | [docs/02_Antenna.md](docs/02_Antenna.md) | `antenna/array_design.py` → element CSV/JSON, beam patterns |
| 4. Enclosure (FreeCAD) | [docs/04_Mechanical.md](docs/04_Mechanical.md) | `mech/build_enclosure.py` → `mech/out/HG1_enclosure.FCStd / .step / *.stl` |
| 5. Render (Blender) | [docs/04_Mechanical.md](docs/04_Mechanical.md) | `mech/render_blender.py` → `render/*.png`, `HG1_scene.blend` |
| 6. Firmware | [firmware/README.md](firmware/README.md) | Versal DSP chain + tracker (C++), STM32 housekeeping (C), simulator + verification |

## Regenerate everything

```bash
python analysis/system_budget.py
```

```bash
python antenna/array_design.py
```

```bash
"C:/Program Files/KiCad/10.0/bin/python.exe" board/generate_boards.py
```

```bash
"C:/Program Files/FreeCAD 1.1/bin/freecadcmd.exe" mech/build_enclosure.py
```

```bash
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P mech/render_blender.py
```

```bash
cmd //c firmware\\build_host.bat
```

```bash
python firmware/sim/gen_scenario.py && firmware/build/hg1_radard.exe --input firmware/sim/out/scenario.iq --out firmware/sim/out && python firmware/sim/verify.py
```

## Honest status

This is a complete **design-stage** package:

- **Computed:** link budget, array and patterns.
- **DRC-clean but unfinished:** board layouts are placed and RF-routed; schematic capture and the remaining digital/power routing are still to do.
- **Modelled:** enclosure and renders.
- **Verified in simulation:** the firmware, against independently synthesised raw ADC data.

Before hardware, it still needs full-wave EM of the element and radome, the custom HRX-8 receiver RFIC (or a COTS brassboard), confirmation of Ku GaN PA availability, thermal CFD, and AIE/PL kernel implementation on the Versal. Open risks are listed in docs/01 §10.
