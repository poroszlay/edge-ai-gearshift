// Compatibility probe only. Actual gearshift integration and measurements: #7.
#include <cstdio>
#include "model_data.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"

namespace {
alignas(16) unsigned char arena[32 * 1024];
}

extern "C" void app_main() {
  const auto* model = tflite::GetModel(model_data);
  if (model->version() != TFLITE_SCHEMA_VERSION) {
    std::printf("MODEL_PROBE FAIL schema\n");
    return;
  }
  tflite::MicroMutableOpResolver<4> resolver;
  if (resolver.AddFullyConnected() != kTfLiteOk || resolver.AddSoftmax() != kTfLiteOk ||
      resolver.AddReshape() != kTfLiteOk || resolver.AddRelu() != kTfLiteOk) {
    std::printf("MODEL_PROBE FAIL resolver\n");
    return;
  }
  tflite::MicroInterpreter interpreter(model, resolver, arena, sizeof(arena));
  if (interpreter.AllocateTensors() != kTfLiteOk) {
    std::printf("MODEL_PROBE FAIL allocate\n");
    return;
  }
  auto* input = interpreter.input(0);
  auto* output = interpreter.output(0);
  if (input->type != kTfLiteInt8 || output->type != kTfLiteInt8 ||
      input->dims->size != 2 || input->dims->data[0] != 1 || input->dims->data[1] != 100 ||
      output->dims->size != 2 || output->dims->data[0] != 1 || output->dims->data[1] != 3) {
    std::printf("MODEL_PROBE FAIL INT8 shapes\n");
    return;
  }
  for (int i = 0; i < 100; ++i) input->data.int8[i] = input->params.zero_point;
  if (interpreter.Invoke() != kTfLiteOk) {
    std::printf("MODEL_PROBE FAIL invoke\n");
    return;
  }
  std::printf("MODEL_PROBE PASS bytes=%u arena_used=%u output=%d,%d,%d\n",
      unsigned(sizeof(model_data)), unsigned(interpreter.arena_used_bytes()),
      output->data.int8[0], output->data.int8[1], output->data.int8[2]);
}
