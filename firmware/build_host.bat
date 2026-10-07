@echo off
rem HoloGuard HG-1 firmware -- host build (MSVC 2022). Builds:
rem   build\hg1_radard.exe   Versal APU radar daemon / reference DSP chain
rem   build\test_dsp.exe     DSP + tracker unit tests
rem   build\test_mcu.exe     STM32 housekeeping firmware against the host BSP model
setlocal
cd /d "%~dp0"
if not defined VCINSTALLDIR call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
if not exist build mkdir build

cl /nologo /std:c++17 /EHsc /O2 /fp:fast /W3 /DNOMINMAX /Idsp\include ^
   dsp\app\hg1_radard.cpp dsp\src\signal_processor.cpp dsp\src\tracker.cpp ^
   /Fobuild\ /Febuild\hg1_radard.exe || exit /b 1

cl /nologo /std:c++17 /EHsc /O2 /W3 /DNOMINMAX /Idsp\include ^
   dsp\test\test_dsp.cpp dsp\src\signal_processor.cpp dsp\src\tracker.cpp ^
   /Fobuild\ /Febuild\test_dsp.exe || exit /b 1

cl /nologo /std:c11 /O2 /W3 /D_CRT_SECURE_NO_WARNINGS /Imcu\include /Imcu\sim /Icommon ^
   mcu\src\power_seq.c mcu\src\thermal.c mcu\src\bit.c mcu\src\link.c mcu\src\app.c ^
   mcu\sim\bsp_sim.c mcu\test\test_mcu.c ^
   /Fobuild\ /Febuild\test_mcu.exe || exit /b 1

echo BUILD OK
endlocal
