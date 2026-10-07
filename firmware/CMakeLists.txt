cmake_minimum_required(VERSION 3.16)
project(hg1_firmware C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_C_STANDARD 11)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

# ---- Versal APU daemon + reference DSP chain (aarch64 Linux or host) ----
add_library(holo dsp/src/signal_processor.cpp dsp/src/tracker.cpp)
target_include_directories(holo PUBLIC dsp/include)
add_executable(hg1_radard dsp/app/hg1_radard.cpp)
target_link_libraries(hg1_radard holo)
add_executable(test_dsp dsp/test/test_dsp.cpp)
target_link_libraries(test_dsp holo)

# ---- STM32 housekeeping firmware, host build against the BSP model ------
add_executable(test_mcu mcu/src/power_seq.c mcu/src/thermal.c mcu/src/bit.c mcu/src/link.c
               mcu/src/app.c mcu/sim/bsp_sim.c mcu/test/test_mcu.c)
target_include_directories(test_mcu PRIVATE mcu/include mcu/sim common)
if(NOT MSVC)
  target_link_libraries(test_mcu m)
endif()

enable_testing()
add_test(NAME dsp COMMAND test_dsp)
add_test(NAME mcu COMMAND test_mcu)
# Target MCU image: build mcu/src + mcu/target in an STM32CubeIDE project
# (STM32G474RETx); see firmware/README.md.
