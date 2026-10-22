#include "measurement.h"

namespace gearshift::measurement {

Result run(Config config, Clock& clock, Workload& workload,
           Record* records, size_t capacity) {
    if (config.count < 1 || config.count > 1000 ||
        config.window_count < 1 || config.window_count > 8 ||
        (config.period_us != 10000 && config.period_us != 20000 &&
         config.period_us != 50000 && config.period_us != 100000)) {
        return {0, 0, Error::invalid_config};
    }
    if (!records || capacity < config.count) return {0, 0, Error::memory_error};
    const int64_t epoch = clock.now_us();
    int64_t busy_until = 0;
    for (size_t i = 0; i < config.count; ++i) {
        Record& r = records[i];
        r = Record{};
        r.index = i;
        r.window_index = i % config.window_count;
        r.scheduled_us = static_cast<int64_t>(i) * config.period_us;
        if (r.scheduled_us < busy_until) {
            r.status = Status::missed;
            continue;
        }
        clock.wait_until_us(epoch + r.scheduled_us);
        const int64_t start = clock.now_us() - epoch;
        if (start >= r.scheduled_us + config.period_us) {
            r.status = Status::missed;
            continue;
        }
        r.started_us = start;
        r.error = workload.prepare(r.window_index);
        if (r.error == Error::none) {
            r.inference_started_us = clock.now_us() - epoch;
            r.error = workload.invoke();
            r.inference_finished_us = clock.now_us() - epoch;
            if (r.error == Error::none) r.error = workload.finish();
        }
        r.finished_us = clock.now_us() - epoch;
        busy_until = r.finished_us;
        r.status = r.error != Error::none ? Status::failed :
                   (r.finished_us > r.scheduled_us + config.period_us ? Status::late : Status::ok);
    }
    clock.wait_until_us(epoch + static_cast<int64_t>(config.count) * config.period_us);
    return {config.count, clock.now_us() - epoch, Error::none};
}

}  // namespace gearshift::measurement
