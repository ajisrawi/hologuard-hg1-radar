/* HoloGuard HG-1 housekeeping MCU -- STM32G474RE target BSP (STM32Cube HAL).
 *
 * Build inside an STM32CubeIDE project generated for STM32G474RETx with:
 *   ADC1 (13 ch scan, DMA circular): VIN PA0, 28V PA1, 5V PA2, 3V3 PA3, NEG5 PC0
 *   (inverting divider), PA drain-current INA186 x6 on PC1 PC2 PC3 PB14 PF0 PB12,
 *   NTC housing PB11, NTC RFIC PB0          (pin map = board/kicad/HG1-DSP.kicad_sch)
 *   SPI1  : ADAR1000 U50/U51 (4-wire, CS_BF0/CS_BF1)  -- PA gate bias DACs, TX VGA
 *   I2C3  : PC8/PC9 -- Versal SYSMON / PMBus (TPS546D24A telemetry), ADS7138 PA-NTC ADC
 *   USART1: Versal link, 921600 8N1, DMA RX circular + DMA TX
 *   COMP1 : PB1 hardware -5 V monitor -> TIM1 BKIN -> forces PA8 (DRAIN_SW, TIM1_CH1) low
 *   IWDG  : 50 ms
 * NOTE: ADAR1000 register addresses / bias-DAC scaling below must be checked
 * against the ADAR1000 datasheet revision used (marked VERIFY).
 */
#include <math.h>
#include <string.h>

#include "bsp.h"
#include "stm32g4xx_hal.h"

extern ADC_HandleTypeDef hadc1;
extern SPI_HandleTypeDef hspi1;
extern I2C_HandleTypeDef hi2c3;
extern UART_HandleTypeDef huart1;
extern IWDG_HandleTypeDef hiwdg;

/* ---------------- pin map (HG1-DSP rev A, U7) ---------------------------- */
typedef struct { GPIO_TypeDef* port; uint16_t pin; bool active_low; } pin_t;
static const pin_t EN_PINS[EN_COUNT] = {
    [EN_NEG5] = {GPIOB, GPIO_PIN_4, false},
    [EN_28V] = {GPIOB, GPIO_PIN_5, false},
    [EN_DRAIN_SW] = {GPIOA, GPIO_PIN_8, false},     /* TIM1_CH1 forced output; BKIN (COMP1) overrides */
    [EN_RF_5V] = {GPIOB, GPIO_PIN_7, false},
    [EN_TX_MUTE_N] = {GPIOB, GPIO_PIN_6, false},    /* drives ADAR1000 TR / PA_ON via J4 */
    [EN_VERSAL] = {GPIOC, GPIO_PIN_6, false},
    [EN_HEATER] = {GPIOC, GPIO_PIN_7, false},
};
static bool en_state[EN_COUNT];
#define PIN_PLL_LD_TX GPIOC, GPIO_PIN_10
#define PIN_PLL_LD_LO GPIOC, GPIO_PIN_11
#define PIN_NEG_PGOOD GPIOC, GPIO_PIN_12
#define PIN_CS_BF0 GPIOA, GPIO_PIN_4
#define PIN_CS_BF1 GPIOA, GPIO_PIN_15

/* ---------------- ADC scan (DMA) ----------------------------------------- */
enum { AD_VIN, AD_28V, AD_5V, AD_3V3, AD_NEG5, AD_ID0, AD_ID5 = AD_ID0 + 5, AD_NTC_H, AD_NTC_R, AD_N };
static volatile uint16_t adc_raw[AD_N];
/* divider ratios (mV at pin -> rail mV) and shunt gain (INA186A3: 100 V/V, 10 mOhm) */
static const float AD_SCALE[AD_N] = {
    [AD_VIN] = 16.0f, [AD_28V] = 11.0f, [AD_5V] = 2.0f, [AD_3V3] = 2.0f, [AD_NEG5] = -2.0f,
    [AD_ID0] = 1.0f, [AD_ID0 + 1] = 1.0f, [AD_ID0 + 2] = 1.0f, [AD_ID0 + 3] = 1.0f, [AD_ID0 + 4] = 1.0f,
    [AD_ID5] = 1.0f, [AD_NTC_H] = 1.0f, [AD_NTC_R] = 1.0f};

static float adc_mv(int ch) { return adc_raw[ch] * (3300.0f / 4095.0f); }

/* Beta-model NTC (10k, B=3435) on 10k pull-up to 3.3 V, result 0.1 degC */
static int32_t ntc_c10(float mv) {
    if (mv < 5.0f) mv = 5.0f;
    if (mv > 3295.0f) mv = 3295.0f;
    const float r = 10000.0f * mv / (3300.0f - mv);
    const float inv_t = 1.0f / 298.15f + logf(r / 10000.0f) / 3435.0f;
    return (int32_t)((1.0f / inv_t - 273.15f) * 10.0f);
}

void bsp_init(void) {
    HAL_ADCEx_Calibration_Start(&hadc1, ADC_SINGLE_ENDED);
    HAL_ADC_Start_DMA(&hadc1, (uint32_t*)adc_raw, AD_N);
    for (int e = 0; e < EN_COUNT; ++e) bsp_enable((bsp_enable_t)e, false);
    HAL_GPIO_WritePin(PIN_CS_BF0, GPIO_PIN_SET);
    HAL_GPIO_WritePin(PIN_CS_BF1, GPIO_PIN_SET);
}

uint32_t bsp_millis(void) { return HAL_GetTick(); }
void bsp_watchdog_kick(void) { HAL_IWDG_Refresh(&hiwdg); }

int32_t bsp_rail_mv(bsp_rail_t r) {
    static const int map[RAIL_COUNT] = {AD_VIN, AD_28V, AD_5V, AD_3V3, AD_NEG5};
    return (int32_t)(adc_mv(map[r]) * AD_SCALE[map[r]]);
}

int32_t bsp_pa_idrain_ma(int pa) {
    /* INA186A3 (100 V/V) on 10 mOhm: 1 mV at ADC = 1 mA */
    return (int32_t)(adc_mv(AD_ID0 + pa) * AD_SCALE[AD_ID0 + pa]);
}

/* PA pedestal NTCs sit behind an I2C ADC (ADS7138, 8 ch) on the ANT board */
static int32_t pa_ntc_c10[HG1_N_PA];
static int32_t versal_c10 = 250;

void bsp_poll_slow(void) {   /* called from the 100 ms slot before thermal_step() */
    uint8_t buf[16];
    if (HAL_I2C_Mem_Read(&hi2c3, 0x10 << 1, 0x00, I2C_MEMADD_SIZE_8BIT, buf, 12, 5) == HAL_OK)
        for (int i = 0; i < HG1_N_PA; ++i)
            pa_ntc_c10[i] = ntc_c10(((buf[2 * i] << 4) | (buf[2 * i + 1] >> 4)) * (3300.0f / 4095.0f));
    /* Versal SYSMON temperature via PMBus READ_TEMPERATURE_1 (0x8D), LINEAR11 */
    if (HAL_I2C_Mem_Read(&hi2c3, 0x32 << 1, 0x8D, I2C_MEMADD_SIZE_8BIT, buf, 2, 5) == HAL_OK) {
        int16_t raw = (int16_t)(buf[0] | (buf[1] << 8));
        int16_t mant = (int16_t)(raw << 5) >> 5, exp = raw >> 11;
        float t = (float)mant * (exp >= 0 ? (float)(1 << exp) : 1.0f / (float)(1 << -exp));
        versal_c10 = (int32_t)(t * 10.0f);
    }
}

int32_t bsp_temp_c10(bsp_temp_t s) {
    if (s < TS_RFIC) return pa_ntc_c10[s];
    if (s == TS_RFIC) return ntc_c10(adc_mv(AD_NTC_R));
    if (s == TS_VERSAL) return versal_c10;
    return ntc_c10(adc_mv(AD_NTC_H));
}

void bsp_enable(bsp_enable_t e, bool on) {
    const pin_t* p = &EN_PINS[e];
    HAL_GPIO_WritePin(p->port, p->pin, (on ^ p->active_low) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    en_state[e] = on;
}
bool bsp_enabled(bsp_enable_t e) { return en_state[e]; }

/* ---------------- ADAR1000 over SPI --------------------------------------- */
/* VERIFY against datasheet: PA bias-on registers CH1..CH4 = 0x29..0x2C,
 * TX VGA gain CH1..CH4 = 0x1C..0x1F, LOAD_WORKING = 0x28. Bias DAC: 0..255
 * maps to 0 .. -4.8 V on the PA_BIAS outputs (~ -18.8 mV / LSB). */
#define ADAR_REG_PA_BIAS_ON(ch) (0x29 + (ch))
#define ADAR_REG_TX_GAIN(ch) (0x1C + (ch))
#define ADAR_REG_LOAD_WORKING 0x28
#define ADAR_BIAS_MV_PER_LSB (-18.8f)
static int32_t vg_cache[HG1_N_PA];

static void adar_write(int dev, uint16_t reg, uint8_t val) {
    uint8_t tx[3] = {(uint8_t)(((dev & 3) << 5) | ((reg >> 8) & 0x07)), (uint8_t)reg, val};
    if (dev == 0) HAL_GPIO_WritePin(PIN_CS_BF0, GPIO_PIN_RESET);
    else HAL_GPIO_WritePin(PIN_CS_BF1, GPIO_PIN_RESET);
    HAL_SPI_Transmit(&hspi1, tx, 3, 2);
    HAL_GPIO_WritePin(PIN_CS_BF0, GPIO_PIN_SET);
    HAL_GPIO_WritePin(PIN_CS_BF1, GPIO_PIN_SET);
}

/* PA k: TX1..TX3 on U50 ch0..2 (left column), TX4..TX6 on U51 ch0..2 */
void bsp_pa_gate_mv(int pa, int32_t mv) {
    int dev = pa % 2, ch = pa / 2;
    float code = (float)mv / ADAR_BIAS_MV_PER_LSB;
    if (code < 0) code = 0;
    if (code > 255) code = 255;
    adar_write(dev, ADAR_REG_PA_BIAS_ON(ch), (uint8_t)(code + 0.5f));
    adar_write(dev, ADAR_REG_LOAD_WORKING, 0x01);
    vg_cache[pa] = mv;
}
int32_t bsp_pa_gate_get_mv(int pa) { return vg_cache[pa]; }

void bsp_tx_atten_db10(int32_t db10) {
    /* VGA ~0.5 dB/LSB near max gain: back-off in 0.5 dB steps from the cal'd setting */
    static const uint8_t TX_GAIN_CAL = 0x7F;
    int32_t steps = (db10 + 2) / 5;
    uint8_t g = (uint8_t)(TX_GAIN_CAL - (steps > 0x3F ? 0x3F : steps));
    for (int dev = 0; dev < 2; ++dev) {
        for (int ch = 0; ch < 3; ++ch) adar_write(dev, ADAR_REG_TX_GAIN(ch), g);
        adar_write(dev, ADAR_REG_LOAD_WORKING, 0x01);
    }
}

bool bsp_pll_locked(void) {
    return HAL_GPIO_ReadPin(PIN_PLL_LD_TX) == GPIO_PIN_SET && HAL_GPIO_ReadPin(PIN_PLL_LD_LO) == GPIO_PIN_SET;
}
bool bsp_neg_rail_pgood(void) { return HAL_GPIO_ReadPin(PIN_NEG_PGOOD) == GPIO_PIN_SET; }

/* ---------------- UART link (DMA ring) ------------------------------------ */
static uint8_t rx_ring[512];
static uint16_t rx_tail;
void bsp_link_start(void) { HAL_UART_Receive_DMA(&huart1, rx_ring, sizeof(rx_ring)); }

int bsp_link_write(const uint8_t* buf, int n) {
    static uint8_t txb[512];
    if (huart1.gState != HAL_UART_STATE_READY || n > (int)sizeof(txb)) return 0;
    memcpy(txb, buf, (size_t)n);
    HAL_UART_Transmit_DMA(&huart1, txb, (uint16_t)n);
    return n;
}

int bsp_link_read(uint8_t* buf, int max) {
    uint16_t head = (uint16_t)(sizeof(rx_ring) - __HAL_DMA_GET_COUNTER(huart1.hdmarx));
    int n = 0;
    while (rx_tail != head && n < max) {
        buf[n++] = rx_ring[rx_tail];
        rx_tail = (uint16_t)((rx_tail + 1) % sizeof(rx_ring));
    }
    return n;
}
