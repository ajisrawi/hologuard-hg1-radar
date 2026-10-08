#!/bin/sh
# Move tuning into the infinite-array unit cell (9 mm, Floquet port on top), broadside.
# Single patch (V), stacked 0.813 (AC) and stacked 1.524 spacer (AE) geometries.
cd "$(dirname "$0")/../.."
PY=./.venv/Scripts/python
$PY antenna/em/element_em.py periodic --nf 13 --f1 13 --f2 19 --tag _PV_single --set par_on=0 drv_l=3.5 stub=2.5 slot_l=2.6 arm_l=0.8
$PY antenna/em/element_em.py periodic --nf 13 --f1 13 --f2 19 --tag _PAC_stk --set drv_l=4.0 par_l=4.6 stub=2.5 slot_l=3.0 arm_l=0.8
$PY antenna/em/element_em.py periodic --nf 13 --f1 13 --f2 19 --tag _PAE_stk152 --set h_par=1.524 drv_l=3.6 par_l=4.6 stub=2.5 slot_l=3.6 arm_l=1.0
echo BATCH_DONE
