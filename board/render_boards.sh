#!/bin/sh
# KiCad 3-D raytraced board renders + STEP models (run after generate_boards.py).
cd "$(dirname "$0")"
CLI="C:/Program Files/KiCad/10.0/bin/kicad-cli.exe"
R="pcb render --quality high --background opaque"
for side in top bottom; do
  "$CLI" $R --side $side --width 1600 --height 1900 -o renders/HG1-ANT_$side.png kicad/HG1-ANT.kicad_pcb
  "$CLI" $R --side $side --width 1800 --height 600 -o renders/HG1-PWR_$side.png kicad/HG1-PWR.kicad_pcb
done
"$CLI" $R --side top --width 1800 --height 1400 --perspective --rotate "-45,0,-20" --zoom 0.72 \
  -o renders/HG1-ANT_iso.png kicad/HG1-ANT.kicad_pcb
"$CLI" $R --side bottom --width 1800 --height 1400 --perspective --rotate "-45,0,20" --zoom 0.72 \
  -o renders/HG1-ANT_iso_bottom.png kicad/HG1-ANT.kicad_pcb
"$CLI" $R --side top --width 1600 --height 1650 -o renders/HG1-DSP_top.png kicad/HG1-DSP.kicad_pcb
mkdir -p step
for b in HG1-ANT HG1-DSP HG1-PWR; do
  "$CLI" pcb export step --force --subst-models -o step/$b.step kicad/$b.kicad_pcb
done
echo RENDER_DONE
