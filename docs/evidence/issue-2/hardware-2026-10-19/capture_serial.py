#!/usr/bin/env python3
"""Capture raw UART bytes from before a controlled EN reset, with timing metadata.

Requires pyserial 3.5. Closing the port occurs after the observation ends.
Usage: python capture_serial.py PORT SECONDS OUTPUT.log
"""
import datetime
import json
import pathlib
import sys
import time

import serial

port, seconds, output = sys.argv[1:]
duration = float(seconds)
uart = serial.Serial(port=None, baudrate=115200, timeout=0.2)
uart.dtr = False
uart.rts = False
uart.port = port
uart.open()
uart.reset_input_buffer()
start_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
start = time.monotonic()
# CP2102 RTS drives EN (active low); DTR stays deasserted (normal SPI boot).
# Open the output before releasing EN so that the ROM boot is captured.
uart.rts = True
time.sleep(0.1)
records = []
try:
    with pathlib.Path(output).open("wb") as log:
        uart.rts = False
        while time.monotonic() - start < duration:
            data = uart.read(4096)
            if data:
                offset = log.tell()
                log.write(data)
                log.flush()
                records.append({"elapsed_s": time.monotonic() - start,
                                "offset": offset, "bytes": len(data)})
finally:
    elapsed = time.monotonic() - start
    uart.close()
    pathlib.Path(output + ".json").write_text(json.dumps({
        "port": port, "baud": 115200, "start_utc": start_utc,
        "elapsed_s": elapsed, "requested_s": duration,
        "controlled_reset": "RTS/EN pulse 100 ms, DTR deasserted",
        "chunks": records,
    }, indent=2) + "\n")
print(f"Captured {elapsed:.3f} s to {output}")
