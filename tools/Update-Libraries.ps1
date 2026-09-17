# Update-Libraries.ps1 (IAG50cm)
#
# Manually-run: checks GitHub for the latest release of each library IAG50cm actually
# references, compares against what's currently installed on this machine, and
# downloads/installs anything newer. Run from an elevated PowerShell prompt.
#
# Requires: gh (GitHub CLI), already authenticated.
#
# -TcProfile is auto-discovered from this machine's Profiles folder if not given
# explicitly. If auto-discovery finds more than one *.profile file, or none, you
# must pass -TcProfile yourself -- check via
# IAG/specs/steering/brotlib-checking-twincat-xae-version.md.
#
# NOTE: the Profiles folder path below (Components\Plc\Profiles) is inferred by
# analogy to plain CODESYS's own Profiles folder -- not yet confirmed for TwinCAT
# specifically. Verify it exists on this machine before trusting auto-discovery;
# if it doesn't, find the real path and pass -TcProfile explicitly instead.
#
# See IAG/specs/design/brotlib-fleet-library-update-automation.md for the full
# design and how RepTool.exe was found.

param(
    # Exactly the custom libraries IAG50cm.plcproj references via PlaceholderReference
    # (excludes Beckhoff Tc2_*/Tc3_* and System_Visu*/VisuDialogs, which ship with XAE
    # itself and aren't managed this way).
    [string[]]$Libraries = @("BROTLib"),
    [string]$TcProfile
)

$LibraryRoot = "C:\ProgramData\Beckhoff\TwinCAT\PlcEngineering\Managed Libraries"
$RepTool = "C:\TwinCAT\3.1\Components\Plc\Common\RepTool.exe"
$ProfilesDir = "C:\TwinCAT\3.1\Components\Plc\Profiles"

if (-not $TcProfile) {
    $profileFiles = Get-ChildItem -Path $ProfilesDir -Filter "*.profile" -ErrorAction SilentlyContinue
    if ($profileFiles.Count -eq 1) {
        $TcProfile = [System.IO.Path]::GetFileNameWithoutExtension($profileFiles[0].Name)
        Write-Host "Auto-discovered profile: $TcProfile" -ForegroundColor Yellow
    } else {
        throw "Could not auto-discover a single profile in $ProfilesDir (found $($profileFiles.Count)). Pass -TcProfile explicitly."
    }
}

foreach ($lib in $Libraries) {
    Write-Host "=== $lib ===" -ForegroundColor Cyan

    $latestTag = gh release view -R "BROTLib/$lib" --json tagName -q .tagName
    if (-not $latestTag) {
        Write-Warning "Could not fetch latest release for $lib -- skipping"
        continue
    }
    $latestVersion = $latestTag.TrimStart("v")

    # Find any already-installed version, regardless of which "Company" folder it's under
    $installedDirs = Get-ChildItem -Path $LibraryRoot -Recurse -Directory -Filter $lib -ErrorAction SilentlyContinue
    $installedVersions = @()
    foreach ($d in $installedDirs) {
        $installedVersions += Get-ChildItem -Path $d.FullName -Directory | Select-Object -ExpandProperty Name
    }

    if ($installedVersions -contains $latestVersion) {
        Write-Host "  Already up to date ($latestVersion)"
        continue
    }

    Write-Host "  Installed: $($installedVersions -join ', '); latest: $latestVersion -- updating"

    $tempDir = Join-Path $env:TEMP "libupdate-$lib"
    New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
    gh release download $latestTag -R "BROTLib/$lib" -p "*.library" -D $tempDir --clobber

    $libFile = Get-ChildItem -Path $tempDir -Filter "*.library" | Select-Object -First 1
    if (-not $libFile) {
        Write-Warning "  No .library asset found on release $latestTag for $lib -- skipping"
        continue
    }

    # RepTool.exe installs every .library file found in the given directory
    # (recursively), independent of any project/source -- this is what the
    # TwinCAT installer itself uses internally for the same purpose, and what
    # the community "snappy" CLI tool wraps for the exact same use case.
    & $RepTool --profile="$TcProfile" --installLibsRecursNoOverwrite $tempDir
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  Installed $($libFile.Name) ($latestVersion)" -ForegroundColor Green
    } else {
        Write-Warning "  RepTool exited $LASTEXITCODE installing $($libFile.Name) -- check output above"
    }
}
