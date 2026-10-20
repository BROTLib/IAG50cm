# Plan: #4 FB_PointingModelForward at the zenith

Issue: [#4](https://github.com/BROTLib/IAG50cm/issues/4) "[Low] FB_PointingModelForward: unclamped ASIN at the zenith".
File: `IAG50cm/POUs/Pointing/FB_PointingModelForward.TcPOU`. Status: plan only, no code changed yet.

## Problem

```
sin_alt := SIN(dec) * sin_lat + COS(dec) * cos_lat * cos_TAU;
alt := ASIN(sin_alt);
cos_alt := COS(alt);
alt_diff := -omega * (1/SQRT(1 - sin_alt*sin_alt)) * COS(dec) * cos_lat * SIN(tau);
```

Two separate failures at the zenith (`dec = lat`, `tau = 0`):

1. `sin_alt` can round to `1 + 2.2E-16`, and `ASIN` of that is NaN (22 of 361 latitudes, -90..90 in 0.5 deg steps).
   NaN goes through `cos_alt` into every velocity term.
2. When `sin_alt` rounds to exactly `1.0`, `1/SQRT(0)` is +Inf, and `Inf * SIN(tau)` is NaN at `tau = 0` or Inf for a
   tiny `tau`. A clamp does not fix this. Python port with IEEE doubles, `HA = 0, Dec = Lat`: the velocity outputs are
   non-finite at **287 of 361** latitudes. At the site latitude (51.5592378) `sin_alt` is `1 - 1.1E-16` at `tau = 0`,
   which is still finite. But `|dec - lat|` below about 1E-8 rad together with a small `tau` while tracking through the
   meridian gives exactly `1.0`, and then Inf.

Effect: `HourAngle_velocity` / `Declination_velocity` go to `fHourAngleVelocity` / `fDeclinationVelocity` and from
there straight into `fbHourAngle.Velocity` / `fbDeclination.Velocity` while tracking (`FB_TelescopeControl`,
around lines 1984-2004). A NaN velocity sent to the axis is the real risk. The **position** corrections
(`HourAngle_correction`, `Declination_correction`) do not use `alt`, `cos_alt` or `alt_diff`, so they are finite at the
zenith. `FB_PointingModelInversion` reads only these corrections and is not affected.

On the telescope (2026-10-12, e2821ab) a slew to El 89.9 showed no NaN. Exactly 90 deg was not tried.

## Root cause

`alt_diff` is d(alt)/dt = d(sin alt)/dt / cos(alt). Its `1/cos(alt)` factor is a 0/0 at the zenith. But **every** use
of `alt_diff` in the block is multiplied by `cos_alt` again:

| line | term |
|---|---|
| `track_tau_esti` refraction, 2nd term | `alt_diff * cos_alt * (...)` |
| `track_dec_esti` refraction, 1st term | `alt_diff * ((cos_alt * sin_DEC) / ...)` |
| `track_dec_esti` refraction, 2nd term | `alt_diff * cos_alt * (...)` |
| `track_dec_esti` flexure | `alt_diff * ((cos_alt * sin_DEC) / cos_DEC)` |

So the model only needs `alt_diff * cos_alt = d(sin alt)/dt = -omega * cos_dec * cos_lat * sin_tau`. This is finite
and smooth everywhere and has no division. The singularity comes only from dividing by `cos_alt` and then
multiplying by it again.

## Change

Exact algebraic rewrite, no epsilon in the output path:

```
// alt difference estimation (WITHOUT Nutation, Aberation, Presession)
sin_alt := sin_DEC * sin_lat + cos_DEC * cos_lat * cos_TAU;
sin_alt := LIMIT(-1.0, sin_alt, 1.0);              // rounding can give 1 + 2.2E-16 at the zenith (#4)
alt     := ASIN(sin_alt);                           // diagnostics only, not used below
cos_alt := SQRT(1.0 - sin_alt * sin_alt);           // = COS(alt), >= 0
// d(sin alt)/dt = cos(alt) * d(alt)/dt; finite everywhere, also at the zenith where d(alt)/dt is 0/0 (#4)
sin_alt_rate := -omega * cos_DEC * cos_lat * sin_TAU;
IF cos_alt > 1.0E-9 THEN
	alt_diff := sin_alt_rate / cos_alt;             // diagnostics only
ELSE
	alt_diff := 0.0;
END_IF
```

Every `alt_diff * cos_alt` (and `alt_diff * ((cos_alt * ...` ) in the four velocity lines becomes
`sin_alt_rate * (...)`, for example:

```
track_tau_esti := track_tau_esti - c_refr_tau * sin_alt_rate * ((sin_TAU * cos_lat) / (sin_alt*sin_alt * cos_DEC)); // 2nd term
track_dec_esti := track_dec_esti - c_refr_dec * sin_alt_rate * (sin_DEC / (cos_DEC * sin_alt)); //# 1ST term
track_dec_esti := track_dec_esti - c_refr_dec * sin_alt_rate * ((sin_lat - sin_alt * sin_DEC) / (cos_DEC * sin_alt*sin_alt)); //# 2nd derivative term
track_dec_esti := track_dec_esti + c_flex_dec * sin_alt_rate * (sin_DEC / cos_DEC);
```

Also: new `VAR sin_alt_rate : LREAL;`, and use the precomputed `sin_DEC` / `cos_DEC` / `sin_TAU` instead of repeating
`SIN(dec)` / `COS(dec)` / `SIN(tau)` (this gives the same values). Leave the `off_*` lines alone. They do not change at
all, so pointing and the inversion give the same results.

**Epsilon (1E-9, diagnostics only).** `alt_diff` stays only so it can still be watched online. It no longer feeds any
output, so its guard cannot change behaviour. `cos_alt = 1E-9` is about 0.2 mas from the zenith. Below that,
`sin_alt_rate / cos_alt` is rounding noise divided by rounding noise. The true limit depends on the direction of
approach, so 0 is as good as any other value.

**Behaviour after the change**

- Zenith: all four outputs are finite and continuous, and they equal the analytic formula. There is no special case,
  no frozen value and no dropped refraction term.
- Off the zenith: the result is the same as today up to rounding (Python port: max |diff| 1.8E-12 deg/s over
  HA -90..90, Dec -30..87, site latitude).
- Horizon (`sin_alt -> 0`): unchanged. The refraction terms still divide by `sin_alt` and `sin_alt^2` and are singular
  for a target exactly on the horizon. Axis motion is already gated by `fHorizon` / `fPointingSafeAltitude` (5 deg).
  This plan does not cover it, see the open questions.
- Pole (`cos_DEC -> 0`): unchanged. `COS(PI/2)` is 6E-17, not 0, so the values get huge but stay finite. Gated by
  `fPoleZone` (|dec| <= 87, 1/cos about 19x). For a separate pole topic see BROTLib#27 / `fix/hour-angle-offset-pole`.

## Tests

1. **Python (offline, no runtime):** add `testing/check_pointing_zenith.py`, stdlib only, in the same style as
   `testing/check_pointing_inversion.py`. It ports the forward model as it is now and as it will be after the change,
   including the velocities, with the GVL_Pointing coefficients. Checks:
   - Zenith sweep: `Dec = Lat`, `HA in {0, +-1E-6, +-1E-3}` deg, Lat -89.5..89.5 in 0.5 steps. The new model gives
     only finite outputs. The current model reproduces the issue (22 latitudes with `sin_alt > 1`, 287 non-finite).
   - Continuity: around the zenith (offsets 1E-9..1 deg in HA and Dec) the new velocities match the analytic formula
     to 1E-12 deg/s, and `sin_alt_rate` matches a central finite difference of `sin_alt` over time (step 1 s,
     relative 1E-6). The finite difference is computed independently, so the test does not just check the formula
     against itself.
   - Equivalence: on a grid away from the zenith/horizon/pole, |new - old| <= 1E-11 deg/s and the corrections are
     bitwise equal.

   Run it with `python testing/check_pointing_zenith.py` (exit code != 0 on a failure).
2. **TcUnit (CI):** add `FB_PointingModelForward_Tests` to IAG50cmTests:
   - `IAG50cmTests/tools/Sync-Sources.ps1`: also copy `IAG50cm/POUs/Pointing/FB_PointingModelForward.TcPOU` and
     `IAG50cm/GVLs/GVL_Pointing.TcGVL` (the coefficients are globals). Add both to the test project's `.gitignore` and
     `IAG50cmTests.plcproj`.
   - Tests: `Zenith_Is_Finite` (loop over latitudes, `Dec = Lat`, `HA = 0` and +-1E-6), `Near_Zenith_Is_Continuous`
     (compare with the value at a 1E-3 deg offset within a tolerance), `Corrections_Unchanged` (a few reference
     points with the expected values from the Python port). ST has no `ISNAN`, so the finiteness check is
     `AssertTrue(ABS(x) < 1.0E3)`, which is FALSE for NaN and Inf.
   - Add a row to the table in `IAG50cmTests/README.md`. CI (`tests.yml`) then runs the suite on every push, with no
     workflow change.

## Risks

- Floating-point traps: if the PLC runtime ever enables FPU exceptions, the remaining horizon division would trap
  instead of giving Inf. Same as today, not made worse.
- A wrong sign or term while editing the four lines. The equivalence test against the current code covers this.
- `alt_diff` changes meaning slightly in the online watch (0 instead of Inf/NaN at the zenith). Nothing reads it.

## Verification on the telescope

Plan T4 step 7. After the TcUnit suite passes, deploy and check:

1. Goto/slew to exactly El 90.0 (Az 180), then start tracking through the meridian at `Dec = Lat`.
2. Watch `fbPointingForward.sin_alt`, `alt_diff`, `sin_alt_rate`, `fHourAngleVelocity`, `fDeclinationVelocity`.
   They must stay finite, and the velocities must stay close to sidereal (about 0.0039 deg/s HA) with no jump.
3. Check all numeric telemetry for NaN/Inf, as in the 2026-10-12 test. Also repeat El 89.9.

## Rollout

- One PR to `develop`: `fix/4-pointing-zenith`, with the POU, the Python check, the TcUnit suite and the
  Sync-Sources/README changes.
- Version: patch release, cut with `release.yml` (it bumps `Global_Version` / `ProjectVersion`). Do not bump the
  version by hand in the PR.
- There is no CHANGELOG file. Release notes (PR / GitHub release): "Tracking velocities from the pointing model are now
  finite at the zenith (#4); pointing corrections unchanged."

## Open questions

1. **Zenith behaviour (working decision, to confirm):** the rewrite above makes the velocities finite and continuous
   at the zenith without special cases. That is better than both options asked about earlier (refraction-rate term 0,
   or freezing the last good value), because it is the exact limit. Is that OK, or should a fallback (for example
   freezing the last finite value if an output is ever non-finite) be added as well?
2. Should the horizon singularity (`/ sin_alt` in the refraction terms, Inf for a target exactly on the horizon) be
   fixed here or in a separate issue? Recommendation: separate issue. Motion is already gated, but the outputs are
   computed every cycle.
3. The issue says a copy of the file is in MONETN/IAG50cm. Should the same fix be ported there?
