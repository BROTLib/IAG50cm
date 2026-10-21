<#
.SYNOPSIS
  Copies the function blocks under test from IAG50cm/POUs into the IAG50cmTests PLC project.

.DESCRIPTION
  XAE cannot link files from outside the project folder (it refuses to load a project that does), so the test
  project holds copies. They are git-ignored and made here, so the tests always run against the code that is
  activated on the telescope. CI runs this before the build; run it by hand before opening the project in XAE.
#>
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$dest = Join-Path $PSScriptRoot '..\IAG50cmTests\IAG50cmTests\POUs'
foreach ($n in 'FB_StopTransaction', 'FB_HomeDropReason', 'FB_HomeHold', 'FB_SweepStop') {
  Copy-Item (Join-Path $repo "IAG50cm\POUs\$n.TcPOU") $dest -Force
  Write-Host "Copied $n.TcPOU"
}
# FB_PointingModelForward reads the fitted coefficients from GVL_Pointing
Copy-Item (Join-Path $repo 'IAG50cm\POUs\Pointing\FB_PointingModelForward.TcPOU') $dest -Force
Write-Host 'Copied FB_PointingModelForward.TcPOU'
Copy-Item (Join-Path $repo 'IAG50cm\GVLs\GVL_Pointing.TcGVL') $dest -Force
Write-Host 'Copied GVL_Pointing.TcGVL'
# The telescope state machine and what it compiles against (mock rig, spike S0 of the unification plan): the closure of
# FB_TelescopeControl in IAG50cm/POUs, found with a comment-blind reference search. The dome, focus and cover blocks are
# not copied, they are mocks (FB_DomeMock, FB_FocusMock, FB_CoversMock).
foreach ($f in 'FB_TelescopeControl.TcPOU', 'FB_HourAngleControl.TcPOU', 'FB_DeclinationControl.TcPOU', 'FB_AxisControl.TcPOU',
              'FB_LatchHome.TcPOU', 'FB_CabinetControl.TcPOU', 'Pointing\FB_PointingModelInversion.TcPOU',
              'Functions\F_HourAngleOffsetOnAxis.TcPOU', 'Functions\F_RoundLREAL.TcPOU', 'Functions\NCError_TO_STRING.TcPOU') {
  Copy-Item (Join-Path $repo "IAG50cm\POUs\$f") $dest -Force
  Write-Host "Copied $f"
}
Copy-Item (Join-Path $repo 'IAG50cm\DUTs\ST_TelescopeConfig.TcDUT') $dest -Force
Write-Host 'Copied ST_TelescopeConfig.TcDUT'
