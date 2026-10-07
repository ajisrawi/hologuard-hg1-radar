/* HoloGuard HG-1 housekeeping MCU -- target entry point (STM32G474).
 * CubeMX-generated init (SystemClock_Config, MX_*_Init) lives in the IDE
 * project; this file wires it to the portable application in ../src.
 */
#include "hg1_mcu.h"
#include "stm32g4xx_hal.h"

void SystemClock_Config(void);
void MX_GPIO_Init(void);
void MX_DMA_Init(void);
void MX_ADC1_Init(void);
void MX_SPI1_Init(void);
void MX_I2C1_Init(void);
void MX_USART1_UART_Init(void);
void MX_COMP1_Init(void);
void MX_TIM1_Init(void);
void MX_IWDG_Init(void);
void bsp_init(void);
void bsp_link_start(void);
void bsp_poll_slow(void);

static app_t app;
static volatile uint32_t tick_flag;

/* SysTick hook (1 kHz) */
void HAL_IncTick(void) {
    uwTick += uwTickFreq;
    tick_flag = 1;
}

int main(void) {
    HAL_Init();
    SystemClock_Config();          /* 170 MHz from 24 MHz HSE */
    MX_GPIO_Init();
    MX_DMA_Init();
    MX_ADC1_Init();
    MX_SPI1_Init();
    MX_I2C1_Init();
    MX_USART1_UART_Init();
    MX_COMP1_Init();               /* -5 V window comparator -> TIM1 break -> drain switch off */
    MX_TIM1_Init();
    MX_IWDG_Init();

    bsp_init();
    bsp_link_start();
    app_init(&app);

    uint32_t last_slow = 0;
    for (;;) {
        if (!tick_flag) {
            __WFI();
            continue;
        }
        tick_flag = 0;
        const uint32_t now = HAL_GetTick();
        if (now - last_slow >= 100) {
            last_slow = now;
            bsp_poll_slow();
        }
        app_tick_1ms(&app, now);
    }
}
