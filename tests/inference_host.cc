// Explicit native protocol fixture. Not the MLP and never hardware evidence.
#include "device.h"
#include <iostream>
#include <string>
using namespace gearshift::inference;
struct HostPlatform : Platform {
    int64_t time=0;
    int64_t now_us() override { return time; }
    void wait_until_us(int64_t t) override { time=std::max(time,t); }
    void drain() override { time+=7000; }
    cJSON* memory() override { auto* m=cJSON_CreateObject(); cJSON_AddNumberToObject(m,"fixture_bytes",0); return m; }
    void minimum_start() override {}
    void minimum_stop() override {}
    bool simulated() override { return true; }
};
struct HostRuntime : Runtime {
    HostPlatform& clock;
    int8_t in[100]{}, out[3]{-128,100,-100};
    explicit HostRuntime(HostPlatform& p):clock(p){}
    Error ready() override { return Error::none; }
    int8_t* input() override { return in; }
    const int8_t* output() override { return out; }
    Error invoke() override { clock.time+=25000; return Error::none; }
    float scale() override { return .005345386452972889f; }
    int zero() override { return -60; }
    const char* model_id() override { return "native_test_double"; }
    const char* dataset_id() override { return "fixture"; }
    size_t model_bytes() override { return 0; }
    size_t arena_bytes() override { return 0; }
};
int main() {
    static HostPlatform platform;
    static HostRuntime runtime(platform);
    static Device device(runtime,platform);
    std::string line;
    while(std::getline(std::cin,line)) {
        cJSON* request=cJSON_Parse(line.c_str());
        cJSON* reply=request ? device.handle(request) : device.framing_error("invalid_json");
        char* data=cJSON_PrintUnformatted(reply);
        if(!data) return 1;
        std::cout<<data<<'\n';
        cJSON_free(data); cJSON_Delete(reply); cJSON_Delete(request);
    }
}
