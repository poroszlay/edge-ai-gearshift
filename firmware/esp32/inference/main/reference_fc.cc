// Use the pinned TFLM reference FC instead of ESP-NN's optimized requantizer.
// Only the exported registration names differ; the upstream kernel is intact.
#define Register_FULLY_CONNECTED Register_FULLY_CONNECTED_REFERENCE
#define RegisterInference_FULLY_CONNECTED RegisterInference_FULLY_CONNECTED_REFERENCE
#include "tensorflow/lite/micro/kernels/fully_connected.cc"
