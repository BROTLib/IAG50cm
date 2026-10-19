# IAG50cmTests

TcUnit tests for pure-logic function blocks of the IAG50cm application (IAG50cm#120). A separate PLC project, so no
test code ends up in the telescope project. It holds copies of the tested files from `IAG50cm/POUs` (XAE cannot link files from outside the project folder). They are
git-ignored and made by `tools/Sync-Sources.ps1`, which CI runs before the build, so the tests always run against the
code that is activated on the telescope. Run it by hand before opening the project in XAE.

## What is covered

| Suite | Tests | What it checks |
|---|---|---|
| `FB_StopTransaction_Tests` | `FB_StopTransaction` | the #108/#117 stop: one `MC_Stop` per axis and stop transaction, also for a stop that never finishes or is rejected (no retrigger), an axis at standstill gets none, `Begin()` starts a new transaction, outputs are one-scan pulses, `bFinished` when the telescope is at rest |
| `FB_HomeDropReason_Tests` | `FB_HomeDropReason` | the WARN and end-state text when a pending home is dropped after 2 min: not ready, stop did not finish, axes busy, and their priority |

`FB_TelescopeControl._StopTelescope` and the `tonHomePending` block call these function blocks, so the paths that cannot
be reached on the real axes (a stop that never reports Done, a stuck stop behind a `gohome`) are tested here.

Not covered: the 30 s command timeout (`tonCommandTimeout`) and the axis blocks themselves; they need the whole
`FB_TelescopeControl` or an NC axis.

## Running

Same as BROTLibTests (see `BROTLib/BROTLibTests/README.md`): TcUnit must be installed, the user-mode runtime running
and licensed.

```
powershell -File tools\Sync-Sources.ps1
TcBuild build IAG50cmTests.sln
powershell -File tools\Run-Tests.ps1
```

CI: `.github/workflows/tests.yml` does this on every push (self-hosted runner, same queue as BROTLib's tests).
