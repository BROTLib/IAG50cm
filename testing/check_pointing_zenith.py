"""FB_PointingModelForward at the zenith (IAG50cm#4).

Line-by-line port of the ST before and after the fix. stdlib `math` only.

Before: alt := ASIN(sin_alt) is NaN when sin_alt rounds to 1 + 2.2E-16, and
alt_diff := ... / SQRT(1 - sin_alt^2) is Inf/NaN when sin_alt rounds to exactly 1.0. Both reach the velocity outputs.
After: sin_alt is clamped and the four velocity terms use d(sin alt)/dt = alt_diff * cos_alt, which has no division.

Checks (exit code 1 on a failure):
  1. the old model reproduces the issue at the zenith, the new one is finite there
  2. the new velocities are continuous around the zenith and sin_alt_rate matches a finite difference of sin_alt
  3. away from zenith/horizon/pole new == old (corrections bitwise, velocities to 1E-11 deg/s)

Coefficients from GVL_Pointing.TcGVL.

Run: python check_pointing_zenith.py
"""
import math
import sys

d2r = math.pi / 180.0
OMEGA = 360.0 / 86164.099 * d2r

C = dict(
    mAl_tau=0.01687078, mEl_tau=-0.02608578, Coll_tau=0.29826615,
    Refr_tau=-0.00759962, Enc_tau=0.00108764, Flex_tau=-0.02462705, NP_tau=0.02128217,
    mAl_dec=0.01606325, mEl_dec=-0.05749048, Coll_dec=-0.17376101,
    Refr_dec=0.01678090, Flex_dec=-0.01915146,
)
LAT_SITE = 51.5592378


def div(a, b):
    """IEEE division as the PLC does it (Python raises on /0)."""
    if b == 0.0:
        return math.nan if a == 0.0 or math.isnan(a) else math.copysign(math.inf, a) * math.copysign(1.0, b)
    return a / b


def asin(x):
    return math.asin(x) if -1.0 <= x <= 1.0 else math.nan


def forward(ha, dec_deg, lat_deg, fixed, c=C):
    """Port of FB_PointingModelForward. Returns (tau_corr, dec_corr, tau_vel, dec_vel, sin_alt)."""
    tau, dec, lat = ha * d2r, dec_deg * d2r, lat_deg * d2r
    sin_tau, cos_tau = math.sin(tau), math.cos(tau)
    sin_dec, cos_dec = math.sin(dec), math.cos(dec)
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)

    sin_alt = sin_dec * sin_lat + cos_dec * cos_lat * cos_tau
    if fixed:
        sin_alt = max(-1.0, min(1.0, sin_alt))
        alt = asin(sin_alt)
        cos_alt = math.sqrt(1.0 - sin_alt * sin_alt)
        sin_alt_rate = -OMEGA * cos_dec * cos_lat * sin_tau
        alt_diff = sin_alt_rate / cos_alt if cos_alt > 1.0e-9 else 0.0
    else:
        alt = asin(sin_alt)
        cos_alt = math.cos(alt) if not math.isnan(alt) else math.nan
        root = math.sqrt(1.0 - sin_alt * sin_alt) if sin_alt * sin_alt <= 1.0 else math.nan
        alt_diff = -OMEGA * div(1.0, root) * math.cos(dec) * cos_lat * math.sin(tau)

    off_tau = -c["mAl_tau"] * (cos_tau * sin_dec / cos_dec)
    off_tau += c["mEl_tau"] * (sin_tau * sin_dec / cos_dec)
    off_tau += c["Coll_tau"]
    off_tau += c["Refr_tau"] * div(sin_tau * cos_lat, sin_alt * cos_dec)
    off_tau += c["Flex_tau"] * (sin_tau * cos_lat / cos_dec)
    off_tau += c["Enc_tau"] / cos_dec
    off_tau -= c["NP_tau"] * (sin_dec / cos_dec)

    trk_tau = c["mAl_tau"] * OMEGA * (sin_tau * sin_dec / cos_dec)
    trk_tau += c["mEl_tau"] * OMEGA * (cos_tau * sin_dec / cos_dec)
    trk_tau += c["Refr_tau"] * OMEGA * div(cos_tau * cos_lat, sin_alt * cos_dec)
    if fixed:
        trk_tau -= c["Refr_tau"] * sin_alt_rate * div(sin_tau * cos_lat, sin_alt * sin_alt * cos_dec)
    else:
        trk_tau -= c["Refr_tau"] * alt_diff * cos_alt * div(sin_tau * cos_lat, sin_alt * sin_alt * cos_dec)
    trk_tau += c["Flex_tau"] * OMEGA * (cos_tau * cos_lat / cos_dec)

    off_dec = c["mAl_dec"] * sin_tau
    off_dec += c["mEl_dec"] * cos_tau
    off_dec += c["Coll_dec"]
    off_dec += c["Refr_dec"] * div(sin_lat - sin_alt * sin_dec, cos_dec * sin_alt)
    off_dec -= c["Flex_dec"] * ((sin_lat - sin_alt * sin_dec) / cos_dec)

    trk_dec = c["mAl_dec"] * OMEGA * cos_tau
    trk_dec -= c["mEl_dec"] * OMEGA * sin_tau
    if fixed:
        trk_dec -= c["Refr_dec"] * sin_alt_rate * (sin_dec / (cos_dec * sin_alt))
        trk_dec -= c["Refr_dec"] * sin_alt_rate * div(sin_lat - sin_alt * sin_dec, cos_dec * sin_alt * sin_alt)
        trk_dec += c["Flex_dec"] * sin_alt_rate * (sin_dec / cos_dec)
    else:
        trk_dec -= c["Refr_dec"] * alt_diff * div(cos_alt * sin_dec, cos_dec * sin_alt)
        trk_dec -= c["Refr_dec"] * alt_diff * cos_alt * div(sin_lat - sin_alt * sin_dec, cos_dec * sin_alt * sin_alt)
        trk_dec += c["Flex_dec"] * alt_diff * (cos_alt * sin_dec / cos_dec)

    return off_tau, off_dec, (trk_tau + OMEGA) / d2r, trk_dec / d2r, sin_alt


def finite(*xs):
    return all(math.isfinite(x) for x in xs)


failures = []


def check(ok, msg):
    print(("ok   " if ok else "FAIL ") + msg)
    if not ok:
        failures.append(msg)


lats = [-89.5 + 0.5 * i for i in range(0, 360)]
has = (0.0, 1e-6, -1e-6, 1e-3, -1e-3)

# 1. zenith sweep
old_bad = sum(1 for lat in lats if not finite(*forward(0.0, lat, lat, False)[2:4]))
over_one = sum(1 for lat in lats if forward(0.0, lat, lat, False)[4] > 1.0)
new_bad = [(lat, ha) for lat in lats for ha in has if not finite(*forward(ha, lat, lat, True))]
print(f"old model, HA=0 Dec=Lat: {old_bad} of {len(lats)} latitudes non-finite, {over_one} with sin_alt > 1")
check(old_bad > 0, "old model reproduces the issue")
check(not new_bad, f"new model finite at the zenith for all latitudes and HA offsets ({len(new_bad)} bad)")

# 2. continuity and independent finite difference
worst = 0.0
for lat in (LAT_SITE, 0.0, 30.0, -45.0):
    for off in (1e-9, 1e-6, 1e-3, 1e-1, 1.0):
        for dha, ddec in ((off, 0), (-off, 0), (0, off), (0, -off), (off, off)):
            v = forward(dha, lat + ddec, lat, True)[2:4]
            z = forward(0.0, lat, lat, True)[2:4]
            worst = max(worst, abs(v[0] - z[0]), abs(v[1] - z[1]))
print(f"max velocity jump within 1 deg of the zenith: {worst:.3e} deg/s")
check(worst < 1e-3, "velocities continuous around the zenith")

worst = 0.0
for lat in (LAT_SITE, 0.0, 30.0, -45.0):
    for ha in (0.0, 1e-3, 0.5, 5.0, -20.0, 60.0):
        for dec in (lat, lat + 1.0, lat - 20.0, 10.0):
            if abs(dec) > 87:
                continue
            tau, d, l = ha * d2r, dec * d2r, lat * d2r
            step = 1.0   # s; HA grows with omega
            def sa(t):
                tt = tau + OMEGA * t
                return math.sin(d) * math.sin(l) + math.cos(d) * math.cos(l) * math.cos(tt)
            fd = (sa(step) - sa(-step)) / (2 * step)
            rate = -OMEGA * math.cos(d) * math.cos(l) * math.sin(tau)
            worst = max(worst, abs(fd - rate) / max(abs(rate), OMEGA * 1e-3))
print(f"sin_alt_rate vs central finite difference: max relative error {worst:.3e}")
check(worst < 1e-6, "sin_alt_rate matches d(sin alt)/dt")

# 3. equivalence away from the singular directions
dv = 0.0
bitwise = True
n = 0
for lat in (LAT_SITE, 0.0, 30.0, -45.0):
    for ha in range(-90, 91, 5):
        for dec in range(-80, 88, 4):
            old = forward(ha + 0.37, dec + 0.11, lat, False)
            new = forward(ha + 0.37, dec + 0.11, lat, True)
            if not finite(*old) or old[4] < 0.1 or old[4] > 0.9999:
                continue
            n += 1
            bitwise &= old[0] == new[0] and old[1] == new[1]
            dv = max(dv, abs(old[2] - new[2]), abs(old[3] - new[3]))
print(f"{n} grid points: max |new - old| velocity {dv:.3e} deg/s")
check(bitwise, "position corrections bitwise unchanged")
check(dv <= 1e-11, "velocities unchanged away from the zenith")

sys.exit(1 if failures else 0)
