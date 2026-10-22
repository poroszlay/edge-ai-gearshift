#include "measurement.h"
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>

using namespace gearshift::measurement;

struct VirtualClock : Clock {
    int64_t time = 0;
    int64_t now_us() override { return time; }
    void wait_until_us(int64_t target) override { if (time < target) time = target; }
};

// A caller-provided workload using a virtual physical clock, not internal mocks.
struct ExampleWorkload : Workload {
    VirtualClock& clock;
    int64_t pre = 1000, inference = 3000, post = 2000;
    explicit ExampleWorkload(VirtualClock& c) : clock(c) {}
    Error prepare(size_t) override { clock.time += pre; return Error::none; }
    Error invoke() override { clock.time += inference; return Error::none; }
    Error finish() override { clock.time += post; return Error::none; }
};

void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

void separate_measurement_intervals() {
    VirtualClock clock;
    ExampleWorkload work(clock);
    Record records[1];
    const auto result = run({1, 10000, 1}, clock, work, records, 1);
    const auto& r = records[0];
    require(result.error == Error::none && result.count == 1 &&
            r.scheduled_us == 0 && r.started_us == 0 &&
            r.inference_started_us == 1000 && r.inference_finished_us == 4000 &&
            r.finished_us == 6000 && r.status == Status::ok && result.end_us == 10000,
            "inference must be nested inside complete MCU processing");
}

void overload_keeps_original_grid_and_drains_last_job() {
    VirtualClock clock;
    ExampleWorkload work(clock);
    work.pre = work.post = 0;
    work.inference = 25000;
    Record records[4];
    const auto result = run({4, 10000, 2}, clock, work, records, 4);
    require(result.count == 4 && result.end_us == 55000 &&
            records[0].status == Status::late && records[1].status == Status::missed &&
            records[2].status == Status::missed && records[3].status == Status::late &&
            records[1].started_us == -1 && records[1].finished_us == -1 &&
            records[2].scheduled_us == 20000 && records[3].started_us == 30000 &&
            records[1].window_index == 1 && records[3].window_index == 1,
            "25 ms work on 10 ms grid must be late/missed/missed/late, no queue or replacement");
}

void insufficient_storage_is_reported_without_running_work() {
    VirtualClock clock;
    ExampleWorkload work(clock);
    Record record;
    const auto result = run({1, 10000, 1}, clock, work, &record, 0);
    require(result.error == Error::memory_error && result.count == 0 && clock.time == 0,
            "insufficient result storage must be an explicit memory error before any work");
}

void rejects_unbounded_or_unknown_profiles() {
    for (Config config : {Config{0, 10000, 1}, {1001, 10000, 1},
                          {1, 0, 1}, {1, 15000, 1}, {1, 10000, 0}, {1, 10000, 9}}) {
        VirtualClock clock;
        ExampleWorkload work(clock);
        Record records[1001];
        const auto result = run(config, clock, work, records, 1001);
        require(result.error == Error::invalid_config && result.count == 0 && clock.time == 0,
                "only bounded counts, 1..8 windows and the four profiles are accepted");
    }
}

void failed_model_is_not_a_successful_decision() {
    struct BrokenModel : ExampleWorkload {
        using ExampleWorkload::ExampleWorkload;
        Error invoke() override { ExampleWorkload::invoke(); return Error::model_error; }
    };
    VirtualClock clock;
    BrokenModel work(clock);
    Record record;
    const auto result = run({1, 10000, 1}, clock, work, &record, 1);
    require(result.count == 1 && record.status == Status::failed &&
            record.error == Error::model_error && record.finished_us == 4000,
            "model error must retain measured time and must not run postprocessing");
}

void scheduler_does_not_replay_expired_releases() {
    struct DelayedClock : VirtualClock {
        void wait_until_us(int64_t target) override {
            VirtualClock::wait_until_us(target);
            if (time == 0) time = 35000;
        }
    } clock;
    ExampleWorkload work(clock);
    Record records[4];
    run({4, 10000, 1}, clock, work, records, 4);
    require(records[0].status == Status::missed && records[1].status == Status::missed &&
            records[2].status == Status::missed && records[0].started_us == -1 &&
            records[3].started_us == 35000 && records[3].finished_us == 41000 &&
            records[3].status == Status::late,
            "expired slots are missed; late start consumes the original deadline budget");
}

void preemption_at_release_does_not_create_an_expired_started_job() {
    struct PreemptedClock : VirtualClock {
        int64_t now_us() override { const auto value = time; time += 5000; return value; }
    } clock;
    ExampleWorkload work(clock);
    Record record;
    run({1, 10000, 1}, clock, work, &record, 1);
    require(record.status == Status::missed || (record.started_us >= 0 && record.started_us < 10000),
            "clock sampling across preemption must never start an expired release");
}

int main() {
    try {
        separate_measurement_intervals();
        std::cout << "PASS separate_measurement_intervals\n";
        overload_keeps_original_grid_and_drains_last_job();
        std::cout << "PASS overload_keeps_original_grid_and_drains_last_job\n";
        insufficient_storage_is_reported_without_running_work();
        std::cout << "PASS insufficient_storage_is_reported_without_running_work\n";
        rejects_unbounded_or_unknown_profiles();
        std::cout << "PASS rejects_unbounded_or_unknown_profiles\n";
        failed_model_is_not_a_successful_decision();
        std::cout << "PASS failed_model_is_not_a_successful_decision\n";
        scheduler_does_not_replay_expired_releases();
        std::cout << "PASS scheduler_does_not_replay_expired_releases\n";
        preemption_at_release_does_not_create_an_expired_started_job();
        std::cout << "PASS preemption_at_release_does_not_create_an_expired_started_job\n";
    } catch (const std::exception& error) {
        std::cerr << "FAIL " << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
