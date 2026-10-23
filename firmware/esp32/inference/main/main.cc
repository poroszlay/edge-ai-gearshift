#include "device.h"
#include "model_data.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "driver/uart.h"
#include "esp_vfs_dev.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <cstdio>
#include <cstring>
#include <cstdarg>

// TFLM errors become structured records. Even a failed Invoke must not write
// diagnostics to UART inside the measured region.
extern "C" void __wrap_DebugLog(const char*, va_list) {}

using namespace gearshift::inference;
namespace tflite { TFLMRegistration Register_FULLY_CONNECTED_REFERENCE(); }
namespace {
alignas(16) uint8_t arena[32*1024];
class MlpRuntime : public Runtime {
    tflite::MicroMutableOpResolver<4> resolver;
    tflite::MicroInterpreter* interpreter = nullptr;
    TfLiteTensor *in = nullptr, *out = nullptr;
    Error state = Error::model_error;
public:
    void initialize() {
        const auto* model = tflite::GetModel(embedded::model_data);
        if(model->version()!=TFLITE_SCHEMA_VERSION ||
           resolver.AddFullyConnected(tflite::Register_FULLY_CONNECTED_REFERENCE())!=kTfLiteOk || resolver.AddSoftmax()!=kTfLiteOk ||
           resolver.AddReshape()!=kTfLiteOk || resolver.AddRelu()!=kTfLiteOk) return;
        static tflite::MicroInterpreter instance(model,resolver,arena,sizeof(arena));
        interpreter=&instance;
        if(interpreter->AllocateTensors()!=kTfLiteOk) { state=Error::memory_error; return; }
        in=interpreter->input(0); out=interpreter->output(0);
        if(!in || !out || in->type!=kTfLiteInt8 || out->type!=kTfLiteInt8 ||
           in->dims->size!=2 || in->dims->data[0]!=1 || in->dims->data[1]!=100 ||
           out->dims->size!=2 || out->dims->data[0]!=1 || out->dims->data[1]!=3 ||
           in->params.scale!=embedded::input_scale || in->params.zero_point!=embedded::input_zero ||
           out->params.scale!=embedded::output_scale || out->params.zero_point!=embedded::output_zero) return;
        state=Error::none;
    }
    Error ready() override { return state; }
    int8_t* input() override { return in ? in->data.int8 : nullptr; }
    const int8_t* output() override { return out ? out->data.int8 : nullptr; }
    Error invoke() override { return interpreter && interpreter->Invoke()==kTfLiteOk ? Error::none : Error::model_error; }
    float scale() override { return embedded::input_scale; }
    int zero() override { return embedded::input_zero; }
    const char* model_id() override { return embedded::model_id; }
    const char* dataset_id() override { return embedded::dataset_id; }
    size_t model_bytes() override { return sizeof(embedded::model_data); }
    size_t arena_bytes() override { return sizeof(arena); }
};
class EspPlatform : public Platform {
public:
    int64_t now_us() override { return esp_timer_get_time(); }
    void wait_until_us(int64_t target) override {
        for(;;) {
            const int64_t remaining=target-now_us();
            if(remaining<=0) return;
            const int64_t tick=1000000/configTICK_RATE_HZ;
            if(remaining>2*tick) vTaskDelay(remaining/tick-1);
        }
    }
    void drain() override { std::fflush(stdout); uart_wait_tx_done(UART_NUM_0,portMAX_DELAY); }
    void minimum_start() override { ESP_ERROR_CHECK(heap_caps_monitor_local_minimum_free_size_start()); }
    void minimum_stop() override { heap_caps_monitor_local_minimum_free_size_stop(); }
    bool simulated() override { return false; }
    cJSON* memory() override {
        const auto free=heap_caps_get_free_size(MALLOC_CAP_8BIT);
        const auto minimum=heap_caps_get_minimum_free_size(MALLOC_CAP_8BIT);
        const auto largest=heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
        const auto stack=uxTaskGetStackHighWaterMark(nullptr)*sizeof(StackType_t);
        auto* m=cJSON_CreateObject();
        cJSON_AddNumberToObject(m,"free_heap_bytes",free);
        cJSON_AddNumberToObject(m,"minimum_free_heap_bytes",minimum);
        cJSON_AddNumberToObject(m,"largest_free_block_bytes",largest);
        cJSON_AddNumberToObject(m,"stack_high_water_bytes",stack);
        cJSON_AddNumberToObject(m,"model_workspace_bytes",sizeof(arena));
        cJSON_AddNumberToObject(m,"device_state_bytes",sizeof(Device));
        return m;
    }
};

// Prevent adversarial nesting from exhausting the embedded parser's stack.
bool shallow(const char* data) {
    bool quoted=false,escape=false; int depth=0;
    for(const char* p=data;*p;++p) {
        if(quoted) {
            if(escape) escape=false;
            else if(*p=='\\') escape=true;
            else if(*p=='"') quoted=false;
        } else if(*p=='"') quoted=true;
        else if(*p=='[' || *p=='{') { if(++depth>16) return false; }
        else if(*p==']' || *p=='}') --depth;
    }
    return true;
}
}
extern "C" void app_main() {
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM_0,32768,0,0,nullptr,0));
    esp_vfs_dev_uart_use_driver(UART_NUM_0);
    std::setvbuf(stdin,nullptr,_IONBF,0);
    std::setvbuf(stdout,nullptr,_IONBF,0);
    static MlpRuntime runtime;
    runtime.initialize();
    static EspPlatform platform;
    static Device device(runtime,platform);
    static char line[16384];
    for(;;) {
        size_t size=0; bool too_large=false;
        // Idle wait is unbounded; an in-progress frame has an absolute 5s limit.
        uint8_t c;
        while(uart_read_bytes(UART_NUM_0,&c,1,pdMS_TO_TICKS(100))!=1) {}
        const int64_t deadline=platform.now_us()+5000000;
        bool timed_out=false;
        for(;;) {
            if(c=='\n') break;
            if(size<sizeof(line)-1) line[size++]=char(c); else too_large=true;
            if(platform.now_us()>=deadline) { timed_out=true; break; }
            int n=0;
            while((n=uart_read_bytes(UART_NUM_0,&c,1,pdMS_TO_TICKS(10)))!=1 && platform.now_us()<deadline) {}
            if(n!=1) { timed_out=true; break; }
        }
        line[size]='\0';
        const char* end=nullptr;
        cJSON* request=nullptr;
        if(!too_large && !timed_out && shallow(line) && std::strlen(line)==size)
            request=cJSON_ParseWithLengthOpts(line,size+1,&end,true);
        cJSON* reply=too_large ? device.framing_error("message_too_large") :
                     timed_out ? device.framing_error("timeout") :
                     request ? device.handle(request) : device.framing_error("invalid_json");
        char* encoded=cJSON_PrintUnformatted(reply);
        if(encoded && std::strlen(encoded)+1<=16384) std::printf("%s\n",encoded);
        else std::printf("{\"v\":1,\"type\":\"error\",\"code\":\"memory_error\",\"simulated\":false}\n");
        cJSON_free(encoded); cJSON_Delete(reply); cJSON_Delete(request);
        vTaskDelay(1);
        // Framing failures terminate the session. Reset is required to reconnect.
        if(too_large || timed_out || !request) { platform.drain(); return; }
    }
}
