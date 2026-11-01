# Reference hardware and wiring

This is the wiring the software is written against. Adapt `config/*.yaml` to your build.

| Subsystem | Reference part | Notes |
|---|---|---|
| Brain | Jetson Nano | camera, USB mic, speaker; build dlib with CUDA for fast face recognition |
| Body controller | Raspberry Pi 4B | I2C enabled; UART or USB-serial to the Jetson |
| Servo drivers | 3 × PCA9685 (0x40, 0x41, 0x42) | id = board × 16 + channel; see `config/joints.yaml` |
| Servos | High-torque hobby servos (30+) | Power from a separate, adequately rated supply; common ground with the Pi |
| Touch skin ADC | 4 × ADS1115 (0x48–0x4B) | 16 zones; add CD74HC4067 muxes to scale |
| Touch skin | Silicone with resistive sensing layer | Voltage divider per zone; pressure assumed to *raise* the ADC reading |
| Projector | Any HDMI projector | Second display; configure `projector.window_pos` and `projector.quad` |
| XR | Meta Quest 3 | Hand tracking enabled; same network as the Jetson |

Power: never power servos from the Pi's 5 V rail. Add a master cut-off switch and fuse in line with the servo supply.
Safety: test every new joint range with the limb supported and the servo unloaded before enabling full-speed motion.
