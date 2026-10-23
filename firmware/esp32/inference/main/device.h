#pragma once
#include "inference.h"
#include "cJSON.h"

namespace gearshift::inference {
struct Runtime {
    virtual ~Runtime() = default;
    virtual Error ready() = 0;
    virtual int8_t* input() = 0;
    virtual const int8_t* output() = 0;
    virtual Error invoke() = 0;
    virtual float scale() = 0;
    virtual int zero() = 0;
    virtual const char* model_id() = 0;
    virtual const char* dataset_id() = 0;
    virtual size_t model_bytes() = 0;
    virtual size_t arena_bytes() = 0;
};

struct Platform : measurement::Clock {
    virtual void drain() = 0;
    virtual cJSON* memory() = 0;
    virtual void minimum_start() = 0;
    virtual void minimum_stop() = 0;
    virtual bool simulated() = 0;
};

// Bounded device state. JSON parsing/serialization and memory snapshots occur
// outside measurement::run. The caller owns and frees each response.
class Device : public measurement::Workload {
public:
    Device(Runtime& runtime, Platform& platform);
    cJSON* handle(const cJSON* request);
    cJSON* framing_error(const char* code);
    Error prepare(size_t index) override;
    Error invoke() override;
    Error finish() override;
private:
    Runtime& runtime;
    Platform& platform;
    Window windows[8];
    measurement::Record records[1000];
    int8_t outputs[1000][3]{};
    bool fetched[1000]{};
    size_t window_count = 0, record_count = 0, fetched_count = 0, calls = 0;
    bool executed = false;
    char run_id[65]{}, mode[16]{}, batch_id[65]{};
    int64_t previous_end = 0;
    cJSON* response(const cJSON* request, const char* type);
    cJSON* error(const cJSON* request, const char* code);
};
}
