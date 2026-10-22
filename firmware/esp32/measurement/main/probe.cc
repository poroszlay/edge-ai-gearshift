// Standalone measurement evidence producer. No model or device-wire implementation.
#include "measurement.h"
#include <cmath>
#include <cstdio>
#include <cinttypes>
#include <initializer_list>
#include <cstring>

#ifdef ESP_PLATFORM
#include "esp_app_desc.h"
#include "esp_system.h"
#include "esp_random.h"
#include "esp_heap_caps.h"
#include "esp_rom_sys.h"
#include "esp_rom_uart.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#else
#include <chrono>
#endif

using namespace gearshift::measurement;

namespace {

struct ProbeClock : Clock {
#ifdef ESP_PLATFORM
    int64_t now_us() override { return esp_timer_get_time(); }
    void wait_until_us(int64_t target) override {
        // Sleep on the absolute grid; leave one tick for fine waiting.
        // Work is not done in the timer task/ISR. Idle tasks remain schedulable.
        for (;;) {
            const int64_t remaining = target - now_us();
            if (remaining <= 0) return;
            const int64_t tick_us = 1000000 / configTICK_RATE_HZ;
            if (remaining > 2 * tick_us) vTaskDelay(remaining / tick_us - 1);
        }
    }
#else
    int64_t time = 0;
    int64_t now_us() override { return time; }
    void wait_until_us(int64_t target) override { if (time < target) time = target; }
#endif
};

struct Window { int64_t timestamps_ms[20]; float samples[20][5]; };
Window windows[4];
float input[100];
volatile float output_checksum;
Record records[1000];

// This is deliberately a synthetic runtime, NOT an MLP or an inference result.
struct SyntheticWorkload : Workload {
    ProbeClock& clock;
    explicit SyntheticWorkload(ProbeClock& value) : clock(value) {}
    Error prepare(size_t index) override {
        const auto& window = windows[index];
        for (size_t i = 0; i < 20; ++i) {
            const float* s = window.samples[i];
            if (window.timestamps_ms[i] < 0 ||
                (i && window.timestamps_ms[i] - window.timestamps_ms[i - 1] != 50)) {
                return Error::invalid_window;
            }
            for (size_t j = 0; j < 5; ++j) if (!std::isfinite(s[j])) return Error::invalid_window;
            if (s[0] < 0 || s[0] > 80 || s[1] < 0 || s[1] > 1 || s[2] < -10 ||
                s[2] > 10 || (s[3] != 1 && s[3] != 2) || s[4] < 0) return Error::invalid_window;
            input[i * 5] = s[0] / 80;
            input[i * 5 + 1] = s[1];
            input[i * 5 + 2] = s[2] / 10;
            input[i * 5 + 3] = s[3] - 1;
            input[i * 5 + 4] = (s[4] > 10 ? 10 : s[4]) / 10;
        }
        return Error::none;
    }
    Error invoke() override {
        const int64_t target = clock.now_us() + 25000;
#ifdef ESP_PLATFORM
        while (clock.now_us() < target) {}  // Intentional CPU overload, 25 ms.
#else
        clock.wait_until_us(target);
#endif
        return Error::none;
    }
    Error finish() override {
        float sum = 0;
        for (float value : input) sum += value;
        output_checksum = sum;
        return Error::none;
    }
};

struct MemorySnapshot { size_t free, minimum, largest, stack; };

MemorySnapshot snapshot() {
#ifdef ESP_PLATFORM
    return {heap_caps_get_free_size(MALLOC_CAP_8BIT),
            heap_caps_get_minimum_free_size(MALLOC_CAP_8BIT),
            heap_caps_get_largest_free_block(MALLOC_CAP_8BIT),
            uxTaskGetStackHighWaterMark(nullptr) * sizeof(StackType_t)};
#else
    return {};
#endif
}

void memory(const MemorySnapshot& value, bool local_minimum) {
#ifdef ESP_PLATFORM
    std::printf("{\"free_heap_bytes\":%u,\"minimum_free_heap_bytes\":%u,"
                "\"largest_free_block_bytes\":%u,\"stack_high_water_bytes\":%u,",
                static_cast<unsigned>(value.free), static_cast<unsigned>(value.minimum),
                static_cast<unsigned>(value.largest), static_cast<unsigned>(value.stack));
#else
    (void)value;
    std::printf("{\"free_heap_bytes\":null,\"minimum_free_heap_bytes\":null,"
                "\"largest_free_block_bytes\":null,\"stack_high_water_bytes\":null,");
#endif
    std::printf("\"result_buffer_bytes\":%u,\"window_buffer_bytes\":%u,"
                "\"model_workspace_bytes\":null,\"minimum_scope\":\"%s\"}",
                static_cast<unsigned>(sizeof(records)), static_cast<unsigned>(sizeof(windows) + sizeof(input)),
                local_minimum ? "series" : "boot");
}

void nullable_time(const char* name, int64_t value) {
    std::printf(",\"%s\":", name);
    if (value < 0) std::printf("null"); else std::printf("%" PRId64, value);
}

const char* status_name(Status status) {
    switch (status) {
        case Status::ok: return "ok";
        case Status::late: return "late";
        case Status::missed: return "missed";
        case Status::failed: return "failed";
    }
    return "failed";
}

const char* error_name(Error error) {
    switch (error) {
        case Error::none: return "null";
        case Error::invalid_window: return "\"invalid_window\"";
        case Error::model_error: return "\"model_error\"";
        case Error::memory_error: return "\"memory_error\"";
        case Error::invalid_config: return "\"invalid_config\"";
    }
    return "\"invalid_config\"";
}

void drain_uart(ProbeClock& clock) {
    std::fflush(stdout);
#ifdef ESP_PLATFORM
    esp_rom_output_tx_wait_idle(0);
#elif defined(MEASUREMENT_HOST_UART_DRAIN_US)
    // Host-only deterministic transport latency for export regression tests.
    clock.wait_until_us(clock.now_us() + MEASUREMENT_HOST_UART_DRAIN_US);
#endif
    (void)clock;
}

int probe(bool live) {
    for (size_t w = 0; w < 4; ++w) {
        for (size_t i = 0; i < 20; ++i) {
            windows[w].timestamps_ms[i] = static_cast<int64_t>(i) * 50;
            const float sample[5] = {40.0f + w, .4f, 0, 1, 12};
            for (size_t j = 0; j < 5; ++j) windows[w].samples[i][j] = sample[j];
        }
    }
    ProbeClock clock;
    SyntheticWorkload workload(clock);
#ifdef ESP_PLATFORM
    const char* simulated = "false";
    const char* sdk = esp_get_idf_version();
    const unsigned cpu_mhz = esp_rom_get_cpu_ticks_per_us();
    const uint64_t run_id = (static_cast<uint64_t>(esp_random()) << 32) | esp_random();
#else
    const char* simulated = "true";
    const char* sdk = "host_virtual_clock";
    const unsigned cpu_mhz = 0;
    const uint64_t run_id = std::chrono::steady_clock::now().time_since_epoch().count();
#endif
    const unsigned expected_batches = live ? 3 : 16;
    const unsigned expected_tasks = live ? 3 : 12400;
    std::printf("{\"event\":\"run_start\",\"schema\":\"gearshift.measurement.v1\","
                "\"run_id\":\"synthetic-%" PRIu64 "\",\"mode\":\"%s\",\"simulated\":%s,"
                "\"workload\":\"synthetic_delay_25ms\",\"sdk\":\"%s\",\"cpu_mhz\":%u,"
                "\"model_bytes\":null,\"expected_batches\":%u,\"expected_tasks\":%u}\n",
                run_id, live ? "live" : "benchmark", simulated, sdk, cpu_mhz, expected_batches, expected_tasks);
    size_t batch = 0;
    int64_t previous_end = clock.now_us();
    for (int64_t period : {10000, 20000, 50000, 100000}) {
        if (live && period != 50000) continue;
        for (unsigned series = 0; series < (live ? 3U : 4U); ++series) {
            ++batch;
            const size_t count = live ? 1 : (series == 0 ? 100 : 1000);
            const char* phase = live ? "live" : (series == 0 ? "warmup" : "measured");
            if (live) windows[0] = windows[series];
            const int64_t uart_wait = clock.now_us() - previous_end;
            const auto before = snapshot();
            std::printf("{\"event\":\"series_start\",\"batch_id\":\"b%u\",\"phase\":\"%s\","
                        "\"series\":%u,\"period_us\":%" PRId64 ",\"count\":%u,\"window_ids\":[",
                        static_cast<unsigned>(batch), phase, live ? 0 : series, period,
                        static_cast<unsigned>(count));
            if (live) std::printf("\"w%u\"", series);
            else std::printf("\"w0\",\"w1\",\"w2\",\"w3\"");
            std::printf("],\"uart_wait_us\":%" PRId64 ",\"memory\":", uart_wait);
            memory(before, false);
            std::printf("}\n");
            drain_uart(clock);
#ifdef ESP_PLATFORM
            if (heap_caps_monitor_local_minimum_free_size_start() != ESP_OK) return 1;
#endif
            const int64_t complete_uart_wait = clock.now_us() - previous_end;
            const auto result = run({count, period, live ? 1U : 4U}, clock, workload, records, 1000);
            previous_end = clock.now_us();
            if (result.error != Error::none) return 1;
            const auto after = snapshot();
#ifdef ESP_PLATFORM
            heap_caps_monitor_local_minimum_free_size_stop();
#endif
            // No serialization, allocation, UART or heap sampling in run().
            // Capture the local minimum before stopping its monitor.
            std::printf("{\"event\":\"series_memory\",\"batch_id\":\"b%u\",\"memory\":",
                        static_cast<unsigned>(batch));
            memory(after, true);
            std::printf("}\n");
            for (size_t i = 0; i < result.count; ++i) {
                const auto& r = records[i];
                std::printf("{\"event\":\"task\",\"batch_id\":\"b%u\",\"index\":%u,\"window_index\":%u,"
                            "\"scheduled_us\":%" PRId64 ",\"status\":\"%s\",\"error\":%s",
                            static_cast<unsigned>(batch), static_cast<unsigned>(r.index),
                            static_cast<unsigned>(r.window_index), r.scheduled_us,
                            status_name(r.status), error_name(r.error));
                nullable_time("started_us", r.started_us);
                nullable_time("inference_started_us", r.inference_started_us);
                nullable_time("inference_finished_us", r.inference_finished_us);
                nullable_time("finished_us", r.finished_us);
                std::printf("}\n");
#ifdef ESP_PLATFORM
                // UART VFS writes poll the TX FIFO. Let IDLE1 run between
                // records so a long export cannot starve its watchdog.
                // This is outside run(); the next UART pause includes it.
                vTaskDelay(1);
#endif
            }
            std::printf("{\"event\":\"series_end\",\"batch_id\":\"b%u\",\"count\":%u,"
                        "\"end_us\":%" PRId64 ",\"uart_wait_us\":%" PRId64 ",\"uart_during_execution\":false}\n",
                        static_cast<unsigned>(batch), static_cast<unsigned>(result.count), result.end_us, complete_uart_wait);
        }
    }
    std::printf("{\"event\":\"run_complete\",\"batches\":%u,\"tasks\":%u}\n",
                expected_batches, expected_tasks);
    drain_uart(clock);
    return 0;
}
}  // namespace

#ifdef ESP_PLATFORM
extern "C" void app_main() {
#ifdef CONFIG_MEASUREMENT_LIVE
    constexpr bool live = true;
#else
    constexpr bool live = false;
#endif
    if (probe(live) != 0) std::printf("measurement failed\n");
}
#else
int main(int argc, char** argv) { return probe(argc == 2 && std::strcmp(argv[1], "--live") == 0); }
#endif
