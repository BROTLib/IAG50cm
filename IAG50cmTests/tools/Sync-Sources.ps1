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
foreach ($n in 'FB_StopTransaction', 'FB_HomeDropReason') {
  Copy-Item (Join-Path $repo "IAG50cm\POUs\$n.TcPOU") $dest -Force
  Write-Host "Copied $n.TcPOU"
}
