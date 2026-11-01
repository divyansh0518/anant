# ANANT — Dual-Mode AI Humanoid & Medical Training Simulator

> A full-scale (6 ft) 3D-printed humanoid that is both a **socially intelligent conversational companion** and a **touch-responsive standardized-patient simulator** for clinical training, built on a dual-compute architecture and open tooling.

<!-- Replace with your media -->
<p align="center">
  <img src="docs/media/anant_hero.jpg" alt="ANANT humanoid" width="70%"><br>
  <em>ANANT — 6 ft humanoid, silicone face, resistive touch skin.</em>
</p>

**Demo video:** `docs/media/demo.mp4` &nbsp;|&nbsp; **Full media folder:** [Google Drive](https://drive.google.com/drive/folders/1SlCmQSr4eqgc99onE9jpQ5VC3Aau4ee3)

---

## Why ANANT

High-fidelity patient simulators that train clinicians on palpation, auscultation and rare presentations are imported systems costing roughly **₹3–4 crore**, which puts them out of reach for most medical colleges. ANANT explores whether an open, 3D-printed, sensor-rich humanoid can deliver the *interaction* that matters in clinical teaching — a patient who looks at you, talks to you, reacts to where and how hard you press, and can be explained anatomically — at a fraction of that cost.

The same body doubles as a general-purpose **embodied-AI research platform**: face-aware conversation with long-term memory, expressive facial actuation, tactile sensing over a soft skin, and immersive XR teleoperation.

## Highlights

| Capability | Implementation |
|---|---|
| **Full-scale humanoid** | 6 ft, 3D-printed, 30+ high-torque servo actuators (head, face, neck, torso, both arms and hands) |
| **Tactile skin** | Silicone resistive touch skin, 16 zones in the reference config, per-zone baseline calibration, pressure-graded events |
| **Expressive face** | Silicone face actuated by 8+ servos; 7 expression presets (neutral, happy, sad, surprised, pain, angry, thinking) blended with timed transitions |
| **20+ sensors** | Touch zones, camera, microphone array, plus additional proprioceptive and environmental sensing |
| **Dual-compute stack** | **Jetson Nano** (perception, language, voice) + **Raspberry Pi 4B** (real-time servo/sensor control) |
| **Custom link protocol** | CRC-16 framed binary protocol, self-resynchronising parser, heartbeat watchdog and E-STOP |
| **Conversation** | Face recognition, per-person contextual memory (SQLite), real-time offline speech recognition, TTS with speech-synchronised jaw motion |
| **Medical mode** | Scenario-driven simulated patient: pressure-aware palpation, rebound tenderness, auscultation sites, vitals, rare-disease cases, timestamped session logs for assessment |
| **Anatomy projection** | Projector-mapped organ overlays on the torso for guided clinical examination |
| **XR teleoperation** | Meta Quest 3 hand tracking → closed-form arm IK, finger curl mapping, head-driven neck, deadman safety |

## System architecture

```
                         ┌───────────────────────────────────────────────┐
  Meta Quest 3           │                JETSON NANO  ("brain")         │
  hand + head tracking   │                                               │
  (Unity client) ──WS──► │  XR server ─┐                                 │
                         │             ▼                                 │
  Camera ─► FaceID ─────►│  Orchestrator ◄─► LLM (OpenAI-compatible)     │
  Mic ────► Vosk STT ───►│     │   ▲            Memory (SQLite)          │
  Speaker ◄ TTS + jaw ◄──│     │   └─ Medical ScenarioEngine ─► Projector│──► anatomy overlay
                         │     ▼                                         │
                         │  ANANT-Link bridge (heartbeat, tx/rx)         │
                         └─────┬─────────────────────────▲───────────────┘
                               │ joints / expressions    │ touch / status
                               ▼   (UART/USB, CRC-16)    │
                         ┌─────┴─────────────────────────┴───────────────┐
                         │            RASPBERRY PI 4B ("body")           │
                         │  50 Hz slew-limited ServoBank ─► 3× PCA9685 ─► 30+ servos
                         │  25 Hz TouchSkin  ◄─ 4× ADS1115 ◄─ silicone resistive skin
                         │  Watchdog: link lost → hold pose      E-STOP: freeze │
                         └───────────────────────────────────────────────┘
```

**Design rationale.** Perception and language are bursty, GPU-friendly and tolerate latency; motion and sensing need deterministic timing. Splitting them across two computers keeps servo control at a fixed 50 Hz regardless of how long a language-model call takes, and means a crash or stall in the AI stack can never leave actuators uncommanded: the Pi's watchdog freezes the robot in place within one second of losing the Jetson.

## Two modes

### Companion mode
ANANT recognizes returning people by face, greets them by name, recalls what they have told it ("my name is…", "I love robotics"), and answers in natural speech. Every LLM reply starts with an expression tag, which is parsed and sent to the face, so *what ANANT says and how it looks stay coherent*. Idle micro-behaviour (blinks, eye saccades) keeps it alive between turns. Touching the hand, cheek, forehead or shoulder triggers appropriate reactions.

### Medical training mode
Say *"medical mode"*, then *"load scenario appendicitis"*. The LLM role-plays the patient under strict rules (lay language, never reveals the diagnosis, answers only what is asked), while the skin drives physical examination:

- **Palpation**: touch a zone and ANANT reacts according to the scenario's tenderness map and how hard you press.
- **Rebound tenderness**: a deep press followed by a sudden release in the right zone triggers a stronger pain response, the way a real patient would.
- **Auscultation** (*"start auscultation"*): placing the stethoscope on a chest zone returns the finding for that site (text on trainer HUD, optional audio file).
- **Vitals** on request and **projected anatomy** on the torso for the relevant organs (*"show anatomy"*).
- **Session log**: every palpation, rebound, auscultation and question is timestamped and saved as JSON with the scenario's teaching points, ready for structured feedback.

Bundled scenarios (educational use only; they are training aids, not clinical guidance):

| Scenario | Teaching focus |
|---|---|
| `acute_appendicitis` | Pain migration, McBurney's point, rebound tenderness |
| `aortic_stenosis` | Exertional triad, ejection systolic murmur at the aortic area |
| `situs_inversus_totalis` | **Rare case**: dextrocardia, left-sided appendicitis, Kartagener association |

Adding a case is one JSON file in `config/scenarios/`.

## XR teleoperation

A Meta Quest 3 streams head and hand tracking to the Jetson over WebSocket. Positions arrive in a yaw-aligned body frame, are scaled to the robot's reach, and solved with a closed-form two-link IK into shoulder pitch/roll and elbow flexion; wrist roll comes from palm orientation and each finger from a measured curl value. Output is exponentially smoothed and rate-limited. **Safety by design:** motion is only commanded while the operator holds a left-hand middle-finger pinch (deadman); releasing it or losing tracking makes the arms hold position. Current scope is 3-DoF shoulder/elbow retargeting; full 7-DoF IK and wrist pitch/yaw are listed under future work.

## Repository layout

```
anant/
  common/    protocol.py (ANANT-Link), transport.py (serial / TCP-sim), config.py
  pi/        servo.py, touch.py, main.py            → runs on Raspberry Pi 4B
  jetson/    main.py, bridge.py, vision.py, memory.py, llm.py, voice.py,
             medical.py, projector.py, idle.py      → runs on Jetson Nano
  xr/        retarget.py, server.py                  → runs on Jetson Nano
config/      joints, expressions, touch zones, anatomy overlays, system, scenarios/
unity/       AnantTeleopClient.cs                    → Meta Quest 3 client
tests/       protocol, servo/IK, memory, medical engine
docs/        PROTOCOL.md, HARDWARE.md, media/
```

## Quick start

### 0. Try it without any hardware (simulation)

```bash
git clone https://github.com/<you>/anant && cd anant
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt requests websockets && pip install -e . --no-deps
pytest                                              # 13 tests

# terminal 1 — body (type "t 13 2100" to press the right-lower-quadrant, "t 13 0" to release)
python -m anant.pi.main --sim
# terminal 2 — brain, keyboard instead of mic/speaker
python -m anant.jetson.main --sim --text --no-camera --no-projector
```
Then type `load scenario appendicitis`, press zone 13 in terminal 1 and watch the patient react. Point `llm.base_url` in `config/system.yaml` at Ollama / llama.cpp / any OpenAI-compatible endpoint for free-form dialogue.

### 1. Raspberry Pi 4B (body)
```bash
pip install -r requirements-pi.txt && pip install -e . --no-deps
sudo raspi-config   # enable I2C; disable serial console if using the GPIO UART
python -m anant.pi.main
```

### 2. Jetson Nano (brain)
```bash
pip install -r requirements-jetson.txt && pip install -e . --no-deps
sudo apt install espeak-ng aplay
# download a Vosk model into models/ and set voice.vosk_model_path
python -m anant.jetson.main --xr       # add --text / --no-camera / --no-projector as needed
```
Voice commands: `medical mode`, `companion mode`, `load scenario <name>`, `start auscultation`, `palpation`, `what are the vitals`, `show anatomy`, `hide anatomy`, `end session`, `emergency stop`, `resume`.

### 3. Quest 3
Open `unity/AnantTeleopClient.cs` in a Unity project with the Meta XR SDK, set `serverUrl` to the Jetson's IP and build to the headset. See the header comment for the deadman gesture and recentering.

> **Calibrate before powering a real robot.** `config/joints.yaml` ships as a template: set every servo's `min`, `max`, `home` and `sign` with the arm supported and unloaded, and re-measure `projector.quad` whenever the projector or robot moves.

## Engineering notes

- **Deterministic motion.** Every joint is slew-rate limited (per-joint deg/s) and clamped to calibrated limits; expressions are timed transitions so the face never snaps.
- **Fail-safe by default.** Heartbeat watchdog (1 s) holds pose on link loss; E-STOP freezes and rejects commands until cleared; the deadman gates XR; the Jetson issues E-STOP on exit.
- **Hardware-free development.** The same code paths run over a TCP loopback link, so protocol, scenarios and control logic are unit-tested and demoable on a laptop.
- **Offline-first.** Speech recognition, TTS, face recognition and memory run on-device; only the language model endpoint is configurable (local or remote).

## Research directions

ANANT is intended as a platform, not just a build. Natural next steps:

- **Soft and bio-inspired sensing/actuation**: richer multi-modal silicone skin (pressure localization, shear), compliant and tendon-driven facial and finger actuation, learned calibration of skin response.
- **Learning from demonstration**: the XR pipeline already records operator motion; logging synchronized teleoperation + tactile data enables imitation learning of gestures and manipulation primitives.
- **Humanoid control**: full 7-DoF arm IK with joint-limit and self-collision handling, whole-body posture control, and torque/impedance control for safe physical interaction.
- **Assistive and rehabilitation robotics**: tactile examination and guided physical interaction are shared problems with assistive devices; extending the platform toward lower-limb and gait-related simulation is a longer-term goal.
- **Clinical-education evaluation**: controlled studies of learning outcomes, objective scoring from session logs, and expansion of the rare-disease scenario library.

## Project status and limitations

Hardware-facing code (PCA9685, ADS1115, serial link, Vosk, camera) is written against the reference wiring in `docs/HARDWARE.md` and must be calibrated to each build. The simulation stack and unit tests run without hardware; the Quest client is a reference implementation to adapt to your Meta XR SDK version. ANANT is a **training aid**; scenarios are educational and not a substitute for clinical judgment or supervised teaching.

Total build cost: **₹ \<fill in\>** &nbsp;|&nbsp; Build time: **\<fill in\>** &nbsp;|&nbsp; Team: **\<fill in\>**

## Acknowledgements

The mechanical base design of ANANT is built upon **[InMoov](https://inmoov.fr)**, the open-source 3D-printed humanoid created by **Gaël Langevin**. We are grateful to Gaël and the InMoov community for making this work possible. InMoov-derived parts remain under InMoov's license (CC BY-NC); see [NOTICE.md](NOTICE.md). ANANT's integration, skin, face, electronics, software and medical-simulation stack are original extensions.

## License

Software: MIT (see [LICENSE](LICENSE)). Mechanical designs derived from InMoov: CC BY-NC, as above.
