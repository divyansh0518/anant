# ANANT-Link protocol

Binary, little-endian, full-duplex over UART/USB-serial (921600 baud default) or TCP (simulation).

```
0xAA 0x55 | type:u8 | seq:u8 | len:u8 | payload[len] | crc16:u16
```
CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) over `type..payload`. Parser resynchronises on the next SOF after any bad CRC.

| Type | Dir | Payload |
|---|---|---|
| `0x01 HEARTBEAT` | J→P | empty, sent at 10 Hz. Pi holds pose if none for `watchdog_s`. |
| `0x10 JOINTS` | J→P | N × (`id:u8`, `deci-degrees:u16`), N ≤ 85 |
| `0x11 EXPRESSION` | J→P | `expr_id:u8`, `transition_ms:u16` |
| `0x1F ESTOP` / `0x1E ESTOP_CLEAR` | J→P | empty |
| `0x81 TOUCH` | P→J | N × (`zone:u8`, `pressure:u16` 0..4095); 0 = released; only changes are sent |
| `0x82 STATUS` | P→J | `uptime_ms:u32`, `flags:u8` (bit0 estop, bit1 watchdog), `crc_errors:u16` |
