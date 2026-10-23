#pragma once
#include "measurement.h"
#include <algorithm>
#include <cmath>
#include <cstdint>

namespace gearshift::inference {
using measurement::Error;
struct Window {
    char id[65]{};
    char trip[65]{};
    bool valid = false;
    bool prequantized = false;
    int64_t timestamps[20]{};
    double samples[20][5]{};
    int8_t codes[100]{};
};

inline int8_t quantize(float value, float scale, int zero) {
    const float scaled = value / scale;
    // Promote only after float32 division; adding .5 in float32 would swallow
    // the representable neighbor immediately below a half-integer.
    const double rounded = std::copysign(std::floor(std::abs(double(scaled)) + .5), scaled);
    return static_cast<int8_t>(std::max(-128., std::min(127., rounded + zero)));
}

inline Error prepare_input(const Window& window, float scale, int zero, int8_t* output) {
    if (!window.valid) return Error::invalid_window;
    if (!output) return Error::memory_error;
    if (!std::isfinite(scale) || scale <= 0 || zero < -128 || zero > 127) return Error::model_error;
    if (window.prequantized) {
        std::copy(window.codes, window.codes + 100, output);
        return Error::none;
    }
    for (int i = 0; i < 20; ++i) {
        const double* s = window.samples[i];
        if (window.timestamps[i] < 0 || (i && window.timestamps[i] - window.timestamps[i-1] != 50))
            return Error::invalid_window;
        for (int j = 0; j < 5; ++j) if (!std::isfinite(s[j])) return Error::invalid_window;
        if (s[0] < 0 || s[0] > 80 || s[1] < 0 || s[1] > 1 || s[2] < -10 || s[2] > 10 ||
            (s[3] != 1 && s[3] != 2) || s[4] < 0) return Error::invalid_window;
        // Match PC: binary64 scaling, narrow to float32, then quantize.
        const double features[5] = {s[0]/80., s[1], s[2]/10., s[3]-1., std::min(s[4],10.)/10.};
        for (int j = 0; j < 5; ++j) output[i*5+j] = quantize(float(features[j]), scale, zero);
    }
    return Error::none;
}
}
