#pragma once

#include <cstddef>
#include <cstdint>

namespace gearshift::measurement {

enum class Error { none, invalid_window, model_error, memory_error, invalid_config };
enum class Status { ok, late, missed, failed };

struct Clock {
    virtual ~Clock() = default;
    virtual int64_t now_us() = 0;
    virtual void wait_until_us(int64_t target) = 0;
};

struct Workload {
    virtual ~Workload() = default;
    virtual Error prepare(size_t window_index) = 0;
    virtual Error invoke() = 0;
    virtual Error finish() = 0;
};

struct Config {
    size_t count;
    int64_t period_us;
    size_t window_count;
};

struct Record {
    size_t index = 0;
    size_t window_index = 0;
    int64_t scheduled_us = 0;
    int64_t started_us = -1;
    int64_t inference_started_us = -1;
    int64_t inference_finished_us = -1;
    int64_t finished_us = -1;
    Status status = Status::ok;
    Error error = Error::none;
};

struct Result {
    size_t count;
    int64_t end_us;
    Error error;
};

// Times are relative to this invocation's monotonic epoch. No I/O in run().
Result run(Config config, Clock& clock, Workload& workload,
           Record* records, size_t capacity);

}  // namespace gearshift::measurement
