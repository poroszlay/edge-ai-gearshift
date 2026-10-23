#include "device.h"
#include <cstring>
#include <limits>

namespace gearshift::inference {
namespace {
const cJSON* get(const cJSON* node, const char* name) { return cJSON_GetObjectItemCaseSensitive(node, name); }
const char* str(const cJSON* node) { return cJSON_IsString(node) ? node->valuestring : ""; }
bool equal(const cJSON* node, const char* text) { return cJSON_IsString(node) && std::strcmp(str(node), text) == 0; }
bool identity(const cJSON* node) {
    if (!cJSON_IsString(node)) return false;
    const auto length = std::strlen(str(node));
    if (!length || length > 64) return false;
    for (const unsigned char* c = reinterpret_cast<const unsigned char*>(str(node)); *c; ++c)
        if (*c < 32 || *c > 126) return false;
    return true;
}
bool integer(const cJSON* node, double low, double high) {
    return cJSON_IsNumber(node) && std::isfinite(node->valuedouble) &&
           node->valuedouble >= low && node->valuedouble <= high &&
           std::floor(node->valuedouble) == node->valuedouble;
}
void text(cJSON* node, const char* key, const char* value) { cJSON_AddStringToObject(node, key, value); }
void num(cJSON* node, const char* key, double value) { cJSON_AddNumberToObject(node, key, value); }
void codes(cJSON* node, const char* key, const int8_t* values, size_t count) {
    auto* array = cJSON_AddArrayToObject(node, key);
    for (size_t i = 0; i < count; ++i) cJSON_AddItemToArray(array, cJSON_CreateNumber(values[i]));
}
const char* error_code(Error value) {
    switch (value) {
        case Error::invalid_window: return "invalid_window";
        case Error::memory_error: return "memory_error";
        default: return "model_error";
    }
}
bool parse_window(const cJSON* node, Window& window) {
    window = Window{};
    if (!cJSON_IsObject(node) || !identity(get(node,"window_id")) || !identity(get(node,"trip_id"))) return false;
    std::strcpy(window.id, str(get(node,"window_id")));
    std::strcpy(window.trip, str(get(node,"trip_id")));
    const auto* input = get(node,"input_int8");
    if (input) {
        if (get(node,"samples") || get(node,"timestamps_ms") || !cJSON_IsArray(input) || cJSON_GetArraySize(input) != 100) return true;
        for (int i=0;i<100;++i) {
            const auto* v = cJSON_GetArrayItem(input,i);
            if (!integer(v,-128,127)) return true;
            window.codes[i] = static_cast<int8_t>(v->valuedouble);
        }
        window.prequantized = window.valid = true;
        return true;
    }
    const auto* times = get(node,"timestamps_ms");
    const auto* samples = get(node,"samples");
    if (!cJSON_IsArray(times) || cJSON_GetArraySize(times)!=20 ||
        !cJSON_IsArray(samples) || cJSON_GetArraySize(samples)!=20) return true;
    for (int i=0;i<20;++i) {
        const auto* t = cJSON_GetArrayItem(times,i);
        // JSON numbers are binary64. Keep integer timestamps exact on both ends.
        if (!integer(t,0,9007199254740991.)) return true;
        window.timestamps[i] = static_cast<int64_t>(t->valuedouble);
        const auto* row = cJSON_GetArrayItem(samples,i);
        if (!cJSON_IsArray(row) || cJSON_GetArraySize(row)!=5) return true;
        for (int j=0;j<5;++j) {
            const auto* v = cJSON_GetArrayItem(row,j);
            if (!cJSON_IsNumber(v) || !std::isfinite(v->valuedouble)) return true;
            window.samples[i][j] = v->valuedouble;
        }
    }
    window.valid = true;
    return true;
}
}

Device::Device(Runtime& runtime_, Platform& platform_) : runtime(runtime_), platform(platform_) {}
cJSON* Device::response(const cJSON* request, const char* type) {
    auto* reply = cJSON_CreateObject();
    num(reply,"v",1); text(reply,"type",type);
    for (const char* key : {"request_id","run_id","mode"}) {
        const auto* value = get(request,key);
        cJSON_AddItemToObject(reply,key,value ? cJSON_Duplicate(value,true) : cJSON_CreateNull());
    }
    cJSON_AddBoolToObject(reply,"simulated",platform.simulated());
    text(reply,"model_id",runtime.model_id());
    return reply;
}
cJSON* Device::error(const cJSON* request, const char* code) {
    auto* reply = response(request,"error"); text(reply,"code",code); return reply;
}
cJSON* Device::framing_error(const char* code) {
    auto* request = cJSON_CreateObject();
    if (*run_id) { text(request,"run_id",run_id); text(request,"mode",mode); }
    auto* reply = error(request,code); cJSON_Delete(request); return reply;
}
Error Device::prepare(size_t index) {
    ++calls;
    auto state = runtime.ready();
    if (state != Error::none) return state;
    auto result = prepare_input(windows[index],runtime.scale(),runtime.zero(),runtime.input());
    if (result == Error::none) std::copy(runtime.input(),runtime.input()+100,windows[index].codes);
    return result;
}
Error Device::invoke() { return runtime.invoke(); }
Error Device::finish() {
    if (!runtime.output()) return Error::model_error;
    std::copy(runtime.output(),runtime.output()+3,outputs[calls-1]);
    return Error::none;
}
cJSON* Device::handle(const cJSON* r) {
    if (!cJSON_IsObject(r)) return error(r,"invalid_message");
    if (!integer(get(r,"v"),1,1)) return error(r,"unsupported_version");
    if (!identity(get(r,"request_id")) || !identity(get(r,"run_id"))) return error(r,"invalid_identity");
    if (equal(get(r,"type"),"start")) {
        if (*run_id) return error(r,"run_already_started");
        if (!equal(get(r,"mode"),"live") && !equal(get(r,"mode"),"benchmark")) return error(r,"invalid_mode");
        std::strcpy(run_id,str(get(r,"run_id"))); std::strcpy(mode,str(get(r,"mode")));
        previous_end = platform.now_us();
        auto* reply=response(r,"ack");
        text(reply,"dataset_id",runtime.dataset_id());
        text(reply,"input_version","window-v1:20x5:sample-major:fixed-scaling:float32");
        auto* order=cJSON_AddArrayToObject(reply,"class_order");
        for (const char* name : {"downshift","hold","upshift"}) cJSON_AddItemToArray(order,cJSON_CreateString(name));
        num(reply,"input_scale",runtime.scale()); num(reply,"input_zero_point",runtime.zero());
        num(reply,"model_bytes",runtime.model_bytes()); num(reply,"model_workspace_bytes",runtime.arena_bytes());
        text(reply,"model_workspace_storage","static");
        return reply;
    }
    if (!*run_id || !equal(get(r,"run_id"),run_id) || !equal(get(r,"mode"),mode)) return error(r,"run_or_mode_mismatch");
    if (equal(get(r,"type"),"load")) {
        const auto* list=get(r,"windows");
        const int count=cJSON_GetArraySize(list);
        if (!identity(get(r,"batch_id")) || !cJSON_IsArray(list) || count<1 || count>8) return error(r,"invalid_batch");
        if (window_count && (!executed || fetched_count < record_count)) return error(r,"batch_pending");
        // Validate identities before changing accepted state.
        for(int i=0;i<count;++i) {
            const auto* w=cJSON_GetArrayItem(list,i);
            if (!cJSON_IsObject(w) || !identity(get(w,"window_id")) || !identity(get(w,"trip_id"))) return error(r,"invalid_identity");
            for(int j=0;j<i;++j) if(equal(get(cJSON_GetArrayItem(list,j),"window_id"),str(get(w,"window_id")))) return error(r,"invalid_identity");
        }
        for(int i=0;i<count;++i) parse_window(cJSON_GetArrayItem(list,i),windows[i]);
        window_count=count; record_count=fetched_count=0; executed=false;
        std::fill(fetched,fetched+1000,false);
        std::strcpy(batch_id,str(get(r,"batch_id")));
        auto* reply=response(r,"ack"); text(reply,"batch_id",batch_id); num(reply,"count",count); return reply;
    }
    if (equal(get(r,"type"),"execute")) {
        if (!window_count || executed || !equal(get(r,"batch_id"),batch_id)) return error(r,"invalid_state");
        const bool live=std::strcmp(mode,"live")==0;
        const bool quality=equal(get(r,"purpose"),"quality");
        const auto* count=get(r,"count"); const auto* period=get(r,"period_ms");
        if(get(r,"purpose") && !quality) return error(r,"invalid_profile");
        if(quality && (live || !integer(count,double(window_count),double(window_count)) || !integer(period,0,0))) return error(r,"invalid_profile");
        if (live && (!integer(count,1,1) || window_count!=1)) return error(r,"invalid_live_count");
        if (!live && !quality && ((!integer(count,100,1000) || (count->valuedouble!=100 && count->valuedouble!=1000)) ||
            !integer(period,10,100) || (period->valuedouble!=10 && period->valuedouble!=20 && period->valuedouble!=50 && period->valuedouble!=100))) return error(r,"invalid_profile");
        const size_t n=static_cast<size_t>(count->valuedouble);
        const int64_t p=live ? 50000 : quality ? 0 : static_cast<int64_t>(period->valuedouble)*1000;
        auto* before=platform.memory();
        // The JSON request is already entirely in RAM. No logging, allocation,
        // serialization, receive or transmit occurs from drain through run.
        platform.drain(); platform.minimum_start();
        const int64_t uart_wait=platform.now_us()-previous_end;
        calls=0;
        measurement::Result result{n,0,Error::none};
        if(quality) {
            // Quality visits every window exactly once, without a deadline or
            // skips. The periodic benchmark alone uses the #5 scheduler.
            const auto epoch=platform.now_us();
            for(size_t i=0;i<n;++i) {
                auto& rec=records[i]; rec=measurement::Record{};
                rec.index=i; rec.window_index=i;
                rec.started_us=platform.now_us()-epoch;
                rec.error=prepare(i);
                if(rec.error==Error::none) {
                    rec.inference_started_us=platform.now_us()-epoch;
                    rec.error=invoke();
                    rec.inference_finished_us=platform.now_us()-epoch;
                    if(rec.error==Error::none) rec.error=finish();
                }
                rec.finished_us=platform.now_us()-epoch;
                rec.status=rec.error==Error::none ? measurement::Status::ok : measurement::Status::failed;
            }
            result.end_us=platform.now_us()-epoch;
        } else result=measurement::run({n,p,window_count},platform,*this,records,1000);
        previous_end=platform.now_us();
        auto* after=platform.memory(); platform.minimum_stop();
        for(auto* snapshot : {before,after}) {
            num(snapshot,"result_buffer_bytes",sizeof(records)+sizeof(outputs)+sizeof(fetched));
            num(snapshot,"window_buffer_bytes",sizeof(windows));
        }
        if(result.error!=Error::none) { cJSON_Delete(before); cJSON_Delete(after); return error(r,error_code(result.error)); }
        executed=true; record_count=result.count;
        auto* reply=response(r,"ack"); text(reply,"batch_id",batch_id);
        num(reply,"count",record_count); num(reply,"period_ms",p/1000);
        cJSON_AddBoolToObject(reply,"uart_during_execution",false);
        num(reply,"end_us",result.end_us); num(reply,"uart_wait_us",uart_wait);
        auto* memory=cJSON_AddObjectToObject(reply,"memory");
        cJSON_AddItemToObject(memory,"before",before); cJSON_AddItemToObject(memory,"after",after);
        return reply;
    }
    if(equal(get(r,"type"),"fetch")) {
        const auto* offset=get(r,"offset");
        if(!executed || !equal(get(r,"batch_id"),batch_id) || !integer(offset,0,double(record_count)-1)) return error(r,"invalid_offset");
        auto* reply=response(r,"results"); text(reply,"batch_id",batch_id);
        num(reply,"offset",offset->valuedouble); num(reply,"total",record_count);
        auto* list=cJSON_AddArrayToObject(reply,"records");
        const size_t start=static_cast<size_t>(offset->valuedouble), stop=std::min(start+8,record_count);
        size_t call=0;
        for(size_t i=0;i<stop;++i) {
            const auto& rec=records[i];
            const size_t current=call;
            if(rec.started_us>=0) ++call;
            if(i<start) continue;
            if(!fetched[i]) { fetched[i]=true; ++fetched_count; }
            const auto& w=windows[rec.window_index];
            auto* row=cJSON_CreateObject(); cJSON_AddItemToArray(list,row);
            num(row,"index",i); text(row,"window_id",w.id); text(row,"batch_id",batch_id);
            num(row,"scheduled_ms",rec.scheduled_us/1000);
            const bool success=rec.status==measurement::Status::ok || rec.status==measurement::Status::late;
            text(row,"status",success ? (rec.status==measurement::Status::ok ? "ok" : "late") :
                 rec.status==measurement::Status::missed ? "missed" : error_code(rec.error));
            for(const auto& item : {std::pair<const char*,int64_t>{"started_us",rec.started_us},
                {"inference_started_us",rec.inference_started_us},{"inference_finished_us",rec.inference_finished_us},
                {"finished_us",rec.finished_us}}) {
                if(item.second<0) cJSON_AddNullToObject(row,item.first); else num(row,item.first,item.second);
            }
            if(success) {
                num(row,"processing_ms",double(rec.finished_us-rec.started_us)/1000);
                text(row,"model_id",runtime.model_id());
                text(row,"decision_source","int8_mlp");
                const auto* out=outputs[current];
                const size_t label=std::max_element(out,out+3)-out;
                text(row,"decision",label==0 ? "downshift" : label==1 ? "hold" : "upshift");
                codes(row,"input_int8",w.codes,100); codes(row,"output_int8",out,3);
            } else if(rec.status==measurement::Status::failed) text(row,"error",error_code(rec.error));
        }
        return reply;
    }
    return error(r,"unknown_command");
}
}
