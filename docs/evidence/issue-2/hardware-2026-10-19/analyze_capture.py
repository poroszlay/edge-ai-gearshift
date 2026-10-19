#!/usr/bin/env python3
"""Check this run's raw UART logs. Usage: python analyze_capture.py LOG_DIRECTORY"""
import json
import math
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
summary = {}
for name in ("basic", "inference"):
    raw = (root / (name + "-monitor.log")).read_bytes()
    timing = json.loads((root / (name + "-monitor.log.json")).read_text())
    resets = list(re.finditer(rb"rst:[^\r\n]*", raw))
    faults = re.findall(rb"[^\r\n]*(?:Guru Meditation|panic|Brownout|watchdog|failed|abort\(\)|Backtrace|schema version)[^\r\n]*", raw, re.I)
    result = {"capture_elapsed_s": timing["elapsed_s"],
              "start_utc": timing["start_utc"], "bytes": len(raw),
              "reset_lines": [m.group().decode() for m in resets],
              "fault_lines": [line.decode(errors="replace") for line in faults]}
    assert not faults, result
    if name == "basic":
        assert b"Hello world!" in raw
        assert b"silicon revision v3.1, 4MB external flash" in raw
        restart = raw.index(b"Restarting now.")
        assert len(resets) == 2 and resets[1].start() > restart
        assert b"SW_CPU_RESET" in resets[1].group()
        result["intentional_software_restarts"] = 1
    else:
        samples = list(re.finditer(rb"x_value: ([^,\r\n]+), y_value: ([^\r\n]+)", raw))
        assert len(samples) >= 100, len(samples)
        assert len(resets) == 1 and resets[0].start() < samples[0].start()
        later_boots = re.findall(rb"rst:|ets Jul|boot: ESP-IDF", raw[samples[0].start():])
        assert not later_boots, later_boots
        for index, sample in enumerate(samples):
            x, y = (float(value) for value in sample.groups())
            assert math.isfinite(x) and math.isfinite(y)
            assert abs(x - (index % 20) * (2 * math.pi / 20)) < 0.00001, (index, x)
        def observed_at(offset):
            return next(chunk["elapsed_s"] for chunk in timing["chunks"]
                        if chunk["offset"] + chunk["bytes"] > offset)
        first = observed_at(samples[0].end() - 1)
        last = observed_at(samples[-1].end() - 1)
        result.update({"continuous_inferences": len(samples),
                       "complete_20_sample_cycles": len(samples) // 20,
                       "x_sequence_checked": True,
                       "unexpected_boots_after_first_inference": len(later_boots),
                       "first_inference_observed_s": first,
                       "last_inference_observed_s": last,
                       "first_to_last_uart_observation_s": last - first})
    result["status"] = "PASS"
    summary[name] = result
print(json.dumps(summary, indent=2))
