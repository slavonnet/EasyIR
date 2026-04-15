# LG universal bit engine — references and preserved gap notes

## Primary upstream references (must stay cited in this workstream)

- [Arduino-IRremote `ac_LG.h`](https://raw.githubusercontent.com/Arduino-IRremote/Arduino-IRremote/refs/heads/master/src/ac_LG.h)
- [Arduino-IRremote `ac_LG.hpp`](https://raw.githubusercontent.com/Arduino-IRremote/Arduino-IRremote/refs/heads/master/src/ac_LG.hpp)

The `LGProtocol` bitfield layout and command constants in `ac_LG.h` inform how we name feature flags and reserved fields. The TS1201 path in EasyIR still uses a **carrier timing** representation; this module maps a 28-bit logical frame to raw mark/space timings using documented nominal LG timings from the Arduino-IRremote comments (header ~8.9 ms / ~4.15 ms, data ~500 µs marks).

## Preserved gap findings (orchestrator packet — do not delete)

These items document the pre-change baseline and residual limits:

1. The legacy send path still resolves **precomputed profile raw timings** (combinatoric matrix) when universal encoding is disabled or unsupported for the requested action.
2. The earlier LG encoder/decoder lived under the pilot package and was **not wired into** `easyir.send_profile_command` until this workstream added the adapter in `helpers.resolve_profile_raw`.
3. Pilot binding was **model-specific** (P12RK heuristics); universal profiles declare **`easyir_protocol` + flags** instead of implying a single SKU.
4. **Feature coverage remains intentionally bounded**: HA-facing sends still center on mode/temp/fan; additional LG command words from `ac_LG.h` (swing, jet, timers, etc.) are exposed as named capability flags for future vertical slices, not full multi-frame automation here.
5. Strict decode requires **signature `0x88`**, checksum nibble (IRremoteESP8266 LG AC rule), and optional **capability filtering**; unknown command words return a structured failure instead of silently pretending to be HVAC state.
