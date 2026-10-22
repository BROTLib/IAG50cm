# IAG50cmTests

TcUnit tests for pure-logic function blocks of the IAG50cm application (IAG50cm#120). A separate PLC project, so no
test code ends up in the telescope project. It holds copies of the tested files from `IAG50cm/POUs` (XAE cannot link files from outside the project folder). They are
git-ignored and made by `tools/Sync-Sources.ps1`, which CI runs before the build, so the tests always run against the
code that is activated on the telescope. Run it by hand before opening the project in XAE.

## What is covered

| Suite | Tests | What it checks |
|---|---|---|
| `FB_StopTransaction_Tests` | `FB_StopTransaction` | the #108/#117 stop: one `MC_Stop` per axis and stop transaction, also for a stop that never finishes or is rejected (no retrigger); and the #98 settle condition before a home may start: the one-scan false standstill at the start of a stop does not settle it, every stopped axis must report Done, no motion lock (StateDWord bit 29) for 3 scans, a disabled axis counts as done, a lock restarts the count, `Begin()` / `Cancel()` |
| `FB_HomeDropReason_Tests` | `FB_HomeDropReason` | the WARN and end-state text when a pending home is dropped after 2 min: not ready, stop did not finish, axes busy, and their priority |
| `FB_HomeHold_Tests` | `FB_HomeHold` | #113: a stop while the calibration sweep runs holds the homing request until the axis is disabled or reset |
| `FB_SweepStop_Tests` | `FB_SweepStop` | #113: after a stop in the sweep the uncalibrated axes are switched off once the stop has settled and no homing runs (3 scans); calibrated axes stay; `Arm()` / `Cancel()` |
| `FB_PointingModelForward_Tests` | `FB_PointingModelForward` | #4: all outputs finite at the zenith (Dec = Lat, every latitude, HA 0 and +-1E-6 deg), velocities continuous around it, and reference values elsewhere (also in `testing/check_pointing_zenith.py`) |
| `FB_IagRig_Tests` | `FB_TelescopeControl` | the mock rig for the telescope state machine tests (BROTLib plan 2026-10-21-telescope-state-machine-unification, step 0.3): `FB_HourAngleMock`/`FB_DeclinationMock` subclass the real axis blocks with the body replaced by a motion model (`FB_AxisMockCore`), a mock axis homes and reports `MoveDone`, and the real `FB_TelescopeControl` runs on the mocks (`FB_FocusMock`, `FB_CoversMock`, `FB_DomeMock`) without an error. The nested `fbAxis` outputs are written through pointers, and the five cabinet contacts are set TRUE through pointers (unlinked they read FALSE, a cabinet error) |
| `IagStopDuringSlew_Tests` | `FB_TelescopeControl` | step 2 of the unification plan, characterization of a stop during a slew on the mock rig (`FB_IagRig`: mock axes with a stop model, scanned in the MAIN order; each test owns a rig and runs over many PLC cycles, the first ones wait for the astronomical clock): one MC_Stop for the axis that is moving and none for the one at rest (#108), the first scan of a stop only drops the move and the second sends the axis stop (`_StopTelescope`), the stop drops `bSlew`, settles and leaves the telescope ready. They pin what the code does today, they are not a specification |
| `IagResetUnderMotion_Tests` | `FB_TelescopeControl` | step 2 of the unification plan, on the mock rig: a reset without an error is ignored (the slew goes on, nothing is reset or stopped, no safety acknowledge, I:205); a reset with an error resets the errored axis, requests the safety acknowledge and 2.5 s later resets every axis that is errored or not enabled (#11, #55, #103) |
| `IagErrorPark_Tests` | `FB_TelescopeControl` | step 2 of the unification plan, on the mock rig: an axis error disables both axes and starts no emergency park (READY_STATE -1.0; MONET parks); a park during an error closes the covers and parks the dome without moving the mount; the same with the axes off (#54) |
| `IagTimeouts_Tests` | `FB_TelescopeControl` | step 3 of the unification plan, through the time seam (`FB_TelescopeControl.nTimeDivisor`, set per rig, shortens every `FB_TimeoutTimer`): a slew still running after 600 s is software error 16#40; an online telescope without a command parks after 12 h |
| `IagParkDuringPowerOn_Tests` | `FB_TelescopeControl` | step 2 of the unification plan, on the mock rig: a park that arrives during the power-on is dropped by it and the power-on finishes (IAG50cm#109; MONET lets the park win); a stop during the power-on aborts the startup (READY_STATE -2.0), parks nothing and leaves the covers open (#27) |

`FB_TelescopeControl._StopTelescope` and the `tonHomePending` block call these function blocks, so the paths that cannot
be reached on the real axes (a stop that never reports Done, a stuck stop behind a `gohome`) are tested here.

Not covered: the 30 s command timeout (`tonCommandTimeout`) and the axis blocks themselves; they need the whole
`FB_TelescopeControl` or an NC axis.

## Running

Same as BROTLibTests (see `BROTLib/BROTLibTests/README.md`): TcUnit must be installed, the user-mode runtime running
and licensed.

```
powershell -File tools\Sync-Sources.ps1
tctool IAG50cmTests.sln build run --require-license TC1200
```

CI: `.github/workflows/tcbuild.yml` does this on every push (self-hosted runner, same queue as BROTLib's tests).

## Failed checks in CI

TcUnit writes the text of a failed assertion only to the ADS log, which CI cannot see. The scenario tests therefore also call `F_Note` next to every assertion, which appends `test: message;` to `GVL_Diag.sFailures`; `tools/Run-Tests.ps1` prints it as `Failed checks: ...` when a test case failed. A failure without a note comes from a test that does not use `F_Note` (the older suites).
