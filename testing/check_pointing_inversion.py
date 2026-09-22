"""FB_PointingModelForward / FB_PointingModelInversion: how many fixed-point passes does
the inversion actually need, and does this model share BROTLib's near-singularity problem
(https://github.com/BROTLib/BROTLib/issues/17, an alt-az Tpoint model that blew up near
the zenith because nothing clamped the elevation fed into the inversion loop)?

Line-by-line port of the ST. stdlib `math` only, no numpy.

IAG50cm's model is an EQUATORIAL (HourAngle/Declination) mount, not BROTLib's alt-az
model, so the geometry differs. The position-correction terms (off_tau_esti/off_dec_esti
-- all that the inversion loop reads) divide by sin(alt) and cos(dec), not by cos(el).
That makes the singular directions the HORIZON (alt -> 0) and the CELESTIAL POLE
(dec -> +/-90), not the zenith:
  - the 1/cos(alt) term in the forward model (alt_diff) feeds only the *velocity*
    outputs (HourAngle_velocity/Declination_velocity), which the inversion loop never
    reads, so there is no zenith singularity in the quantity being inverted;
  - dec is kept away from the pole by FB_TelescopeControl's fPoleZone (default 3 deg,
    i.e. |dec| <= 87), so 1/cos(dec) stays bounded (~19x at the limit) -- not a
    practical problem;
  - elevation is kept away from the horizon only by fHorizon (default 1.0 deg) --
    and this script shows the fixed-point map is CHAOTIC, not just slow, below about
    alt=2-3 deg: it does not merely need more iterations, it oscillates without
    settling (see "Below alt~2-3 deg" below). A naive port of BROTLib's fix (clamp
    sin(alt) away from 0 inside forward()) was tried and does NOT resolve this -- the
    instability comes from the iterate wandering across HA/Dec space between passes,
    not from a single evaluation's denominator. That is a different, harder problem
    than BROTLib's (whose forward model already self-clamped its trig at 89 deg and
    just needed the loop's own seed clamped to match) and is NOT fixed here; see the
    commit message / conversation for why a guessed clamp was not applied.

Coefficients: real fitted values from GVL_Pointing.TcGVL (21.01.2026, 136 points,
Lukas Melzig; RMS ~15-18 arcsec).

Run: python check_pointing_inversion.py
"""
import math

d2r = math.pi / 180.0

C = dict(
    mAl_tau=0.01687078, mEl_tau=-0.02608578, Coll_tau=0.29826615,
    Refr_tau=-0.00759962, Enc_tau=0.00108764, Flex_tau=-0.02462705, NP_tau=0.02128217,
    mAl_dec=0.01606325, mEl_dec=-0.05749048, Coll_dec=-0.17376101,
    Refr_dec=0.01678090, Flex_dec=-0.01915146,
)


def forward(hour_angle, declination, latitude, c=C):
    """Port of FB_PointingModelForward.TcPOU. Returns (HourAngle_correction, Declination_correction) in degrees."""
    tau = hour_angle * d2r
    dec = declination * d2r
    lat = latitude * d2r

    sin_tau, cos_tau = math.sin(tau), math.cos(tau)
    sin_dec, cos_dec = math.sin(dec), math.cos(dec)
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)

    sin_alt = sin_dec * sin_lat + cos_dec * cos_lat * cos_tau

    off_tau = -c["mAl_tau"] * (cos_tau * sin_dec / cos_dec)
    off_tau += c["mEl_tau"] * (sin_tau * sin_dec / cos_dec)
    off_tau += c["Coll_tau"]
    off_tau += c["Refr_tau"] * (sin_tau * cos_lat / (sin_alt * cos_dec))
    off_tau += c["Flex_tau"] * (sin_tau * cos_lat / cos_dec)
    off_tau += c["Enc_tau"] / cos_dec
    off_tau -= c["NP_tau"] * (sin_dec / cos_dec)

    off_dec = c["mAl_dec"] * sin_tau
    off_dec += c["mEl_dec"] * cos_tau
    off_dec += c["Coll_dec"]
    off_dec += c["Refr_dec"] * ((sin_lat - sin_alt * sin_dec) / (cos_dec * sin_alt))
    off_dec -= c["Flex_dec"] * ((sin_lat - sin_alt * sin_dec) / cos_dec)

    return off_tau, off_dec


def altitude(hour_angle, declination, latitude):
    tau, dec, lat = hour_angle * d2r, declination * d2r, latitude * d2r
    sin_alt = math.sin(dec) * math.sin(lat) + math.cos(dec) * math.cos(lat) * math.cos(tau)
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))


def inversion(hour_angle, declination, latitude, n, epsilon=0.0, c=C):
    """Port of FB_PointingModelInversion.TcPOU (FOR i:=0 TO n-1, early exit at epsilon)."""
    d_ha = d_dec = 0.0
    d_ha_new = d_dec_new = 0.0
    for _ in range(n):
        d_ha, d_dec = d_ha_new, d_dec_new
        d_ha_new, d_dec_new = forward((hour_angle - d_ha) % 360.0, declination - d_dec, latitude, c)
        if abs(d_ha - d_ha_new) <= epsilon / 3600.0 and abs(d_dec - d_dec_new) <= epsilon / 3600.0:
            break
    return d_ha_new, d_dec_new


def residual_arcsec(hour_angle, declination, latitude, n, c=C):
    """Fixed-point residual of the returned offsets, as sky separation (d_ha * cos dec)."""
    d_ha, d_dec = inversion(hour_angle, declination, latitude, n, c=c)
    f_ha, f_dec = forward(hour_angle - d_ha, declination - d_dec, latitude, c)
    return 3600.0 * math.hypot((d_ha - f_ha) * math.cos(declination * d2r), d_dec - f_dec)


if __name__ == "__main__":
    lats = (-30.0, -15.0, 15.0, 50.0)  # representative site latitudes; result is not very latitude-sensitive
    decs = [d / 10.0 for d in range(-870, 871, 10)]  # |dec| <= 87, matching fPoleZone=3deg

    print("Iterations needed for < 0.25\" residual, worst case over the NORMAL operating envelope")
    print("(altitude floor at which the map is well-behaved -- see the chaos check below), by floor:")
    for alt_floor in (10, 5, 4, 3):
        worst_n = 0
        for lat in lats:
            for ha in range(0, 360, 3):
                for dec in decs:
                    if altitude(ha, dec, lat) < alt_floor:
                        continue
                    for n in range(1, 50):
                        if residual_arcsec(ha, dec, lat, n) < 0.25:
                            break
                    else:
                        n = 999
                    worst_n = max(worst_n, n)
        print(f" alt >= {alt_floor:2d} deg: {worst_n} iterations")

    print("\nResidual after n=8 (chosen: comfortable margin over the 5 needed at alt>=3 deg) vs n=20 (current),")
    print("worst case over alt >= 3 deg (the practical envelope once you're clear of the horizon zone):")
    for n in (5, 8, 20):
        worst_r = 0.0
        for lat in lats:
            for ha in range(0, 360, 5):
                for dec in decs:
                    if altitude(ha, dec, lat) < 3.0:
                        continue
                    worst_r = max(worst_r, residual_arcsec(ha, dec, lat, n))
        print(f" n={n:2d}: worst residual {worst_r:.6f}\"")

    print("\nBelow alt~2-3 deg (well inside FB_TelescopeControl's own fHorizon=1.0 deg floor), the fixed-point")
    print("map does not converge -- it oscillates. More iterations do not help; this is a separate,")
    print("unresolved issue (see module docstring), not something this change attempts to fix:")
    lat, ha, dec = -30.0, 0.0, 59.5  # alt ~ 0.5 deg here
    print(f" lat={lat} ha={ha} dec={dec} (altitude {altitude(ha, dec, lat):.2f} deg)")
    d_ha = d_dec = 0.0
    for i in range(15):
        d_ha, d_dec = forward((ha - d_ha) % 360.0, dec - d_dec, lat)
        print(f"  pass {i:2d}: d_ha={d_ha:10.4f}  d_dec={d_dec:12.4f}")
