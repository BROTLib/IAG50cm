# IAG50cm

TwinCAT 3 control application for the **50 cm "Emmy Noether" telescope** of the
Institut für Astrophysik Göttingen (Georg-August-Universität Göttingen). The
telescope is a **German-equatorial (hour angle / declination) mount**
(`ST_TelescopeConfig`: `name := 'Emmy Noether'`, `diameter := 0.5`, `mount :=
'HA_DEC'`) at the institute in Göttingen (lon 9.9452433°, lat 51.5592378°,
alt 100 m).

The application controls the three NC axes (Hour Angle, Declination, Focus),
the Baader dome (azimuth + shutter over RS232), the two relay-driven mirror
covers, the cabinet power monitoring, a serial hand pendant and the TwinSAFE
safety chain (STO/SS1), and publishes MQTT/InfluxDB telemetry. It is built on
the **BROTLib** and **AstroBROT** libraries (namespace `BROT`) and is the
equatorial counterpart to the Alt-Az MONET applications — its axis and pointing
code is being unified with BROTLib (see
[BROTLib/UNIFICATION.md](../BROTLib/UNIFICATION.md)).

---

## Repository layout

```
IAG50cm/
├── IAG50cm.sln                  # TwinCAT solution (RT x86/x64, CE7 ARMV7, OS)
├── IAG50cm.tsproj               # TwinCAT system project (I/O, NC axes, tasks, mappings)
├── TLR_TAN.tclrq                # License request: TC3 IoT (TF6701), TC3 Serial (TF6340)
├── IAG50cm/
│   ├── IAG50cm.plcproj          # PLC project
│   ├── PlcTask.TcTTO            # PLC task (10 ms, priority 20, calls MAIN)
│   ├── PlcTask_Fast.TcTTO       # Fast task (2 ms, priority 19, calls SerialBackground)
│   ├── DUTs/                    # E_MirrorCoverState, ST_TelescopeConfig
│   ├── GVLs/                    # GVL_Pointing, GVL_Safety, GVL_Serial
│   ├── POUs/                    # Program and function blocks (see below)
│   │   ├── MAIN.TcPOU
│   │   ├── FB_TelescopeControl.TcPOU
│   │   ├── FB_HourAngleControl / FB_DeclinationControl / FB_FocusControl
│   │   ├── FB_Axis3 / FB_AxisControl / FB_BaseAxis / FB_LatchHome
│   │   ├── FB_DomeControl / FB_CoverControl / FB_PendantControl
│   │   ├── FB_CabinetControl / FB_SafetyHandling / FB_SerialBackground
│   │   ├── FB_PointingModelForward / FB_PointingModelInversion
│   │   ├── DomeControl/States/, CoverControl/States/, PendantControl/States/
│   │   ├── Functions/           # F_RoundLREAL, NCError_TO_STRING
│   │   └── Testing/FB_RefMarkerSearch.TcPOU
│   ├── VISUs/Safety.TcVIS       # TwinCAT visualization "Safety"
│   └── _Libraries/              # Resolved library references (BROTLib 0.3.0, AstroBROT 0.3.0)
├── EL1918/                      # TwinSAFE safety PLC (E-stop group, FSoE)
├── ELM7212/                     # TwinSAFE Logic terminal — HA + DEC servo drives
├── ELM7221/                     # TwinSAFE Logic terminal — FOCUS servo drive
└── _Boot/                       # Boot project for TwinCAT RT (x86) incl. safety apps
```

---

## Hardware / EtherCAT topology

**Device 1 (EtherCAT)** — coupler Term 1 (`EK1200-5000`), PLC runtime on ADS
port 851:

| Terminal | Type | Function |
|---|---|---|
| Safety (EL1918) | EL1918 | 8-channel TwinSAFE safety input, integrated safety PLC |
| Power Status (EL1808) | EL1808 | 8-channel digital input (cabinet auxiliary contacts) |
| HA DEC (ELM7212-9016) | ELM7212-9016 | 2-channel servo terminal 48 V/4.5 A, OCT, **STO, TwinSAFE Logic** — drives HourAngle (Ch 2) and Declination (Ch 1) |
| MirrorCover1 / MirrorCover2 (EL2652) | EL2652 | 2-channel relay outputs — cover motors |
| Power (EL9110) | EL9110 | Power supply terminal with diagnostics |
| Reset 24V (EL2004) | EL2004 | 4-channel digital output (error LED) |
| Dome Pendant (EL6002) | EL6002 | 2-channel RS232 — Ch 1 pendant, Ch 2 dome |
| Encoder HA / Encoder DEC (EL5021) | EL5021 | 1-channel sin/cos encoders (Heidenhain) |
| FOCUS (ELM7221-9016) | ELM7221-9016 | 1-channel servo terminal 48 V/8 A, OCT, **STO, TwinSAFE Logic** — focus drive |
| Cabinet IN (EL1004) | EL1004 | 4-channel digital input (mode switch, reset button) |
| Safety Out (EL2904) | EL2904 | 4-channel TwinSAFE safety output |
| Term 13 (EL9011) | EL9011 | End terminal |

**PLC runtime:** Beckhoff **CX5110-0115** embedded PC (Windows CE 7.0), TwinCAT
3.1 Build 4024, RT (x86). The three servo drives are the ELM72xx terminals
themselves (STO/SS1 integrated); detailed motor/inverter parameters live in an
external TwinCAT Drive Manager 2 project (not part of this repository).

---

## PLC application architecture

| Task | Cycle | Priority | Entry program |
|---|---|---|---|
| `PlcTask` | 10 ms | 20 | `MAIN` |
| `PlcTask_Fast` | 2 ms | 19 | `SerialBackground` (EL6002 serial I/O) |
| `VISU_TASK` | 200 ms | 30 | TwinCAT visualization |

```
MAIN
├── comm              : FB_Comm_MQTT_Influx          (MQTT + Influx telemetry, BROTLib)
├── telescopeControl  : FB_TelescopeControl          (I_RaDecTelescope, I_Telescope)
├── haControl         : FB_HourAngleControl          (extends FB_AxisControl, I_Axis)
├── decControl        : FB_DeclinationControl        (extends FB_AxisControl, I_Axis)
├── focusControl      : FB_FocusControl              (extends FB_AxisControl, I_Focus)
├── domeControl       : FB_DomeControl               (I_Dome)
├── coverControl      : FB_CoverControl              (I_MirrorCovers)
├── pendantControl    : FB_PendantControl
└── safetyHandling    : FB_SafetyHandling
```

The axis hierarchy is `FB_BaseAxis (ABSTRACT, I_BaseAxis)` →
`FB_AxisControl (ABSTRACT, I_Axis)` → `FB_HourAngleControl` /
`FB_DeclinationControl` / `FB_FocusControl`, each wrapping one NC axis
(`HourAngle`, `Declination`, `Focus`) through the low-level `FB_Axis3`
(MC_Power/Move/Jog/Home, external-setpoint tracking). Dome, covers and pendant
use interface-based state machines (`I_DomeState`, `I_CoverState`,
`I_PendantState` with concrete state FBs).

---

## Key components

### FB_TelescopeControl — the TCS

The heart of the application: a full telescope control system implementing
`I_RaDecTelescope` / `I_Telescope` with the TCS command interface.

- **Commands** (`E_TCSCommand`): `poweron > stop > park > gohome > goto > slew >
  track > no_command`, each a stage-based (`CASE nStage`) state machine with
  command timeouts and event logging; pre-empted commands are interrupted
  cleanly.
- **Power-on sequence**: open covers → enable + calibrate HA/DEC → focus →
  go home → dome tracking.
- **Park**: focus park → dome 180°/park → HA/DEC park → disable drives → close
  covers; auto-park after 12 h without a command. A park during an error or
  with the axes off only closes the covers and parks the dome (the mount is
  not moved). A running park aborted by an error or an E-stop (at any stage)
  logs one `PARK aborted ...` WARN, never `PARK completed`.
- **Time and coordinates**: `FB_AstroClock` → JD (`DateTime2JD`), LST
  (`CT2LST`); conversions `FB_HADEC2RADEC` / `FB_RADEC2HADEC` / `FB_EQ2HOR` /
  `FB_HOR2EQ` (AstroBROT); pointing model forward/inversion
  (`FB_PointingModelForward`, `FB_PointingModelInversion`).
- **Safety checks**: target below horizon (`fHorizon` 1.0°) or in the pole zone
  (`90° − fPoleZone`, 3.0°) → stop and go home once the telescope is ready (a powered-off mount is
  not homed until the power-on); E-stop disables both axes.
- **Outputs**: `bReady`, `fReadyState` (0 shutdown / 0.3 parking / 0.7
  powering / 1.0 ready / −1 error), `nMotionState` (0 stopped / 1 moving /
  8 tracking), `bIsParked`, `bLocalMode`, current/target coordinates.

### Axes and homing

- `FB_HourAngleControl` / `FB_DeclinationControl` — position clamps
  (−180…180° HA, −50…180° Dec), auto-homing on enable
  (`MC_ForceCalibration`), **latch-homing on the Heidenhain encoder reference
  markers** via `FB_LatchHome` (`MC_StepReferencePulseDetection`, three pulses,
  re-detection on the way back), sidereal tracking for HA
  (`omega = 360/86164.099`), soft-limit interlocks, slew-time readout
  (`MC_ReadParameter`), SoE reset.
- `FB_FocusControl` — focus travel 1…17 mm, tolerance 0.005, force-calibration
  homing.
- `FB_Axis3` — generic NC-axis driver with an external-setpoint tracking
  section (`MC_ExtSetPointGenFeed`, `TrackVelocityRef`, tracking envelope).

### Dome, covers, pendant, cabinet

- `FB_DomeControl` — **Baader dome** over RS232 (EL6002 Ch 2): shutter commands
  (`d#opeshut`, `d#closhut`, ...), azimuth slews (`d#aziXXXX`), off-center
  compensation (±5°), Baader west-of-south azimuth convention conversion;
  state machine `Idle / Opening / Closing / Moving / Parking / Homing / Error`.
- `FB_CoverControl` — two mirror covers, each driven by two relay outputs
  (EL2652); staggered open/close (`Delta` 5 s, `TimeToCycle` 15 s), state
  machine `Idle / Opening / Closing / Stopping`; state enum `E_MirrorCoverState`.
- `FB_PendantControl` — serial hand pendant (EL6002 Ch 1): hex command protocol
  for the two-line display and buttons; adjusts HA/Dec/focus **offsets** in
  small/big steps.
- `FB_CabinetControl` — 24 V/48 V auxiliary contacts, fuse box reports, local/
  remote mode switch, reset button, error LED (EL1808/EL1004/EL2004).

### Safety handling and pointing

- `FB_SafetyHandling` — TwinSAFE group startup sequence: wait 2 s → pulse
  `ErrAck` 1 s → pulse `Restart` 1 s → run.
- `FB_PointingModelForward` — TPOINT-style HA/Dec model: mount misalignment
  (`C_mAl`, `C_mEl`), collimation (`C_Coll`), refraction (`C_Refr`), tube
  flexure (`C_Flex`), encoder scale (`C_Enc`), non-perpendicularity (`C_NP`);
  also computes tracking-velocity corrections. `FB_PointingModelInversion`
  inverts it by fixed-point iteration (≤ 20 iterations, 0.25 arcsec).

---

## States and modes

- **Telescope**: power on → (auto-open covers) → enable + calibrate axes →
  go home → goto (RA/Dec) / slew (Alt/Az) / track (sidereal, auto-track after
  goto) / stop / park / reset; **local mode** via the cabinet switch disables
  robotic operation.
- **Dome shutter** follows `E_RoofState` (BROTLib), dome rotation
  `E_DomeRotationState` (BROTLib).
- **Covers**: `closing / opening / stopped / closed / open / error`
  (`E_MirrorCoverState`).

---

## Communication and telemetry

`FB_Comm_MQTT_Influx` (BROTLib) connects to the MQTT broker and publishes
telemetry in Influx line protocol:

| Parameter | Value |
|---|---|
| Broker host | `169.254.149.100` (link-local, operator workstation) |
| Port | `1883` |
| Subscribe topic (commands) | `50cm/Telescope/SET` |
| Publish topic (telemetry) | `50cm/Telemetry` |
| Log topic | `50cm/Log` |

Telemetry follows the TSI/TCI-style `telescope`/`dome` measurement domain:
`TELESCOPE.READY_STATE`, `TELESCOPE.MOTION_STATE`, `TELESCOPE.INFO.*`,
`TELESCOPE.STATUS.GLOBAL` / `.LOCAL_MODE`, `OBJECT.INSTRUMENTAL.DEC/HA`,
`OBJECT.HORIZONTAL.ALT/AZ`, `OBJECT.EQUATORIAL.*`,
`POSITION.INSTRUMENTAL.{DEC,HA,FOCUS}.*`, `POSITION.HORIZONTAL.*`,
`POSITION.EQUATORIAL.*`, `AUXILIARY.DOME.*` and `AUXILIARY.COVER.REALPOS`.
Telemetry rate 1 s while moving/tracking, 5 s otherwise. Events are published
to the log topic via `FB_Eventlog`.

---

## Safety (TwinSAFE)

Three safety projects (FSoE over EtherCAT):

- **EL1918 (TwinSafeGroup1)** — the E-stop group running on the EL1918 safety
  input terminal: `FBMon1` (safeMon, 100 ms) monitors the E-stop chain,
  `FBEdm1` (safeEdm, 500 ms) monitors contactor feedback, `FBOr1`/`FBAnd1`
  derive the **STO** and **ErrAck** signals; restart/error-ack handshake with
  the PLC (`GVL_Safety.Run/Restart/ErrAck`).
- **ELM7212** (HA + DEC drives) and **ELM7221** (FOCUS drive) — TwinSAFE Logic
  servo terminals with their own STO/SS1 error-handling applications
  (`STO_CMD`, `SS1_CMD`, `Error_Ack_CMD`, `STO_STATE`, ...). STO/SS1 commands
  arrive from the EL1918 group over FSoE; `SS1_To_NC` outputs provide the safe
  stop request to the NC.
- **EL2904** — hard-wired safety output terminal.

Safety concept: **E-stop chain (EL1918) → STO + SS1 to all three servo
terminals + EL2904 safety outputs, EDM on contactors, PLC-run/restart/err-ack
handshake**.

## Visualization

A single TwinCAT visualization, `Safety` (`VISUs/Safety.TcVIS`), provides the
safety operator page: ErrAck / Restart toggle switches bound to `GVL_Safety`
and labels for E-stop / STO / EL1904 / EL2904 diagnostics (the diagnostic
function blocks feeding it are currently commented out in `FB_SafetyHandling`).

---

## Configuration

| Parameter | Value |
|---|---|
| Site | lon 9.9452433°, lat 51.5592378°, alt 100 m (Göttingen) |
| Park positions | HA 0.0°, Dec 52.0°, focus 16.3 mm |
| Home positions | HA 0.0°, Dec 52.0°, focus 16.3 mm |
| Slew velocity | 8.0 °/s |
| Horizon / pole zone | 1.0° / 3.0° |
| Axis limits | HA ±180°, Dec −50…180°, focus 1…17 mm |
| Auto-park | 12 h without command |
| Pointing model | 12-term HA/Dec model, calibrated 2026-01-21 from 136 points, RMS HA 17.7″ / RMS Dec 13.5″ (`GVL_Pointing`) |

---

## Dependencies

- **BROTLib** (0.3.0) — `FB_Comm_MQTT_Influx`, `FB_Eventlog`, interfaces
  (`I_Telescope`, `I_RaDecTelescope`, `I_Dome`, `I_Focus`, `I_MirrorCovers`,
  `I_Axis`, `I_BaseAxis`, `I_Comm`), `E_TCSCommand`, `E_RoofState`,
  `E_DomeRotationState`, `ST_RaDecCoordinate`, `ST_AltAzCoordinate`,
  `FB_SoEReset`.
- **AstroBROT** (0.3.0) — `FB_AstroClock`, `FB_EQ2HOR`, `FB_HOR2EQ`,
  `FB_HADEC2RADEC`, `FB_RADEC2HADEC`, `DateTime2JD`, `CT2LST`.
- Beckhoff system libraries: `Tc2_MC2`, `Tc2_MC2_Drive`,
  `Tc3_MC2_AdvancedHoming` (motion), `Tc2_SerialCom` (RS232 dome/pendant),
  `Tc3_IotBase` / `Tc3_IotCommunicator` (MQTT, TF6701), `Tc2_Standard`,
  `Tc2_System`, `Tc2_Utilities`, `Tc3_Module`, plus visualization libraries.

---

## Building and deployment

The solution is built with TwinCAT 3.1 (PLC project authored with 3.1.4026.12;
boot project requires ≥ 3.1.4021) in TwinCAT XAE. Solution configurations
cover TwinCAT RT (x64/x86), TwinCAT CE7 (ARMV7) and TwinCAT OS. The deployed
controller is a **CX5110-0115** running TwinCAT RT (x86); a boot project under
`_Boot/TwinCAT RT (x86)/` includes the compiled PLC (ADS port 851) and the
safety applications (EL1918/ELM7212/ELM7221 `.tfzip`), so the controller boots
directly into the application. Licenses: TC3 IoT Communication (TF6701) and
TC3 Serial Communication (TF6340).

**CI.** `.github/workflows/tcbuild.yml` builds `IAG50cm.sln` with TcBuild on every push (self-hosted runner, never on pull requests). A green run means the project compiles; TcBuild exit code 1 (built with warnings) counts as success. It only compiles; no tests run in CI.
