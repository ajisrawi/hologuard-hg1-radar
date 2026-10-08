#!/bin/sh
# Local verification of the Modal-optimised element (cavity fence on, 1.016 mm parasitic spacer).
cd "$(dirname "$0")/../.."
PY=./.venv/Scripts/python
G="drv_l=3.2127 par_l=4.4806 slot_l=3.0199 arm_l=2.1352 stub=1.5015 h_par=1.016 cav=1"
for a in "0 0" "20 0" "30 0" "40 0" "50 0" "60 0" "20 90" "40 90" "45 45"; do
  set -- $a
  $PY antenna/em/element_em.py periodic --theta $1 --phi $2 --nf 17 --f1 15 --f2 17 --res 0.18 --tag _final --set $G
done
$PY antenna/em/element_em.py isolated --nf 13 --f1 14.5 --f2 17.5 --tag _final --set $G
echo VERIFY_DONE
