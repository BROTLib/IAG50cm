# Update-Libraries.ps1 (IAG50cm)
#
# Manually-run: installs the libraries IAG50cm references that are missing on this
# machine, each in exactly the version the project pins (DefaultResolution of its
# PlaceholderReference in the .plcproj), downloaded from the GitHub release of that
# version. Libraries without a pin (a "*" resolution, or not referenced directly, like
# the transitive AstroBROT of BROTLib) get their latest release; so does everything
# with -Latest. Run from an elevated PowerShell prompt.
#
# Requires: gh (GitHub CLI), already authenticated.
#
# Close TwinCAT XAE before running (it locks the installed libraries), and afterwards
# check in the Library Manager that the placeholder (e.g. BROTLib, *) resolves to the
# version just installed -- XAE can keep resolving an older one; if so, set the
# resolution to the new version explicitly.
#
# -TcProfile is auto-discovered if not given explicitly, by reading TcVersion from
# this repo's own .tsproj (e.g. TcVersion="3.1.4024.66" -> profile
# "TwinCAT PLC Control_Build_4024.66") and matching it against this machine's
# Profiles folder. Falls back to "the one .profile file" if there's exactly one
# and no .tsproj match. If neither works, pass -TcProfile yourself -- check via
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
    # IAG50cm.plcproj only directly references BROTLib via PlaceholderReference, but
    # BROTLib itself references AstroBROT -- TcBuild does not install transitive
    # library dependencies as a side effect, so AstroBROT has to be installed here
    # too for BROTLib's own reference to resolve. (Excludes Beckhoff Tc2_*/Tc3_* and
    # System_Visu*/VisuDialogs, which ship with XAE itself and aren't managed this way.)
    [string[]]$Libraries = @("BROTLib", "AstroBROT"),
    [string]$TcProfile,
    # Ignore the versions pinned in the project and install the newest release of each library.
    [switch]$Latest
)

$LibraryRoot = "C:\TwinCAT\3.1\Components\Plc\Managed Libraries"
$RepTool = "C:\TwinCAT\3.1\Components\Plc\Common\RepTool.exe"
$ProfilesDir = "C:\TwinCAT\3.1\Components\Plc\Profiles"

if (-not $TcProfile) {
    $profileFiles = Get-ChildItem -Path $ProfilesDir -Filter "*.profile" -ErrorAction SilentlyContinue

    $repoRoot = Join-Path $PSScriptRoot ".."
    $tsproj = Get-ChildItem -Path $repoRoot -Recurse -Depth 2 -Filter "*.tsproj" -ErrorAction SilentlyContinue | Select-Object -First 1
    $expectedBuild = $null
    if ($tsproj) {
        $m = Select-String -Path $tsproj.FullName -Pattern 'TcVersion="3\.1\.([\d.]+)"' | Select-Object -First 1
        if ($m) { $expectedBuild = $m.Matches[0].Groups[1].Value }
    }

    if ($expectedBuild) {
        $expectedName = "TwinCAT PLC Control_Build_$expectedBuild"
        $match = $profileFiles | Where-Object { [System.IO.Path]::GetFileNameWithoutExtension($_.Name) -eq $expectedName }
        if ($match) {
            $TcProfile = $expectedName
            Write-Host "Auto-discovered profile from $($tsproj.Name) (TcVersion 3.1.$expectedBuild): $TcProfile" -ForegroundColor Yellow
        } else {
            throw "Project declares TcVersion 3.1.$expectedBuild (expected profile '$expectedName') but no matching .profile file exists in $ProfilesDir. Pass -TcProfile explicitly."
        }
    } elseif ($profileFiles.Count -eq 1) {
        $TcProfile = [System.IO.Path]::GetFileNameWithoutExtension($profileFiles[0].Name)
        Write-Host "Auto-discovered profile (only one present, no .tsproj match): $TcProfile" -ForegroundColor Yellow
    } else {
        throw "Could not determine TcProfile: no .tsproj with a TcVersion found under $repoRoot, and $($profileFiles.Count) profile files present in $ProfilesDir (need exactly 1 to fall back on). Pass -TcProfile explicitly."
    }
}

# Version a project pins for a library: DefaultResolution of its PlaceholderReference
# (e.g. "BROTLib, 0.12.0 (BROT)" -> "0.12.0"). $null if there is none or it is a wildcard.
function Get-PinnedVersion([string]$Library) {
    $plcprojs = Get-ChildItem -Path (Join-Path $PSScriptRoot "..") -Recurse -Depth 2 -Filter "*.plcproj" -ErrorAction SilentlyContinue
    foreach ($p in $plcprojs) {
        $text = Get-Content -Raw -Path $p.FullName
        # The placeholder name can differ from the repo name ("MONET Roof" for MONETRoof).
        foreach ($m in [regex]::Matches($text, '<PlaceholderReference Include="([^"]+)">\s*<DefaultResolution>[^,<]+,\s*([^\s(<]+)')) {
            if (($m.Groups[1].Value -replace ' ', '') -eq $Library -and $m.Groups[2].Value -ne "*") { return $m.Groups[2].Value }
        }
    }
    return $null
}

foreach ($lib in $Libraries) {
    Write-Host "=== $lib ===" -ForegroundColor Cyan

    # Install exactly the version the project pins (DefaultResolution of the library's
    # PlaceholderReference); only without a pin (e.g. "*", or a library the project does
    # not reference directly) or with -Latest is the newest GitHub release taken.
    $pinned = if ($Latest) { $null } else { Get-PinnedVersion $lib }
    if ($pinned) {
        $targetTag = "v$pinned"
        $targetVersion = $pinned
        gh release view $targetTag -R "BROTLib/$lib" --json tagName -q .tagName | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "$lib is pinned to $pinned but release $targetTag does not exist on GitHub -- skipping"
            continue
        }
        Write-Host "  Pinned in project: $pinned"
    } else {
        $targetTag = gh release view -R "BROTLib/$lib" --json tagName -q .tagName
        if (-not $targetTag) {
            Write-Warning "Could not fetch latest release for $lib -- skipping"
            continue
        }
        $targetVersion = $targetTag.TrimStart("v")
        Write-Host "  No pin used (latest release): $targetVersion"
    }

    # Find any already-installed version, regardless of which "Company" folder it's under
    $installedDirs = Get-ChildItem -Path $LibraryRoot -Recurse -Directory -Filter $lib -ErrorAction SilentlyContinue
    $installedVersions = @()
    foreach ($d in $installedDirs) {
        $installedVersions += Get-ChildItem -Path $d.FullName -Directory | Select-Object -ExpandProperty Name
    }

    if ($installedVersions -contains $targetVersion) {
        Write-Host "  Already installed ($targetVersion)"
        continue
    }

    Write-Host "  Installed: $($installedVersions -join ', '); installing: $targetVersion"

    # Start from an empty folder: RepTool installs everything in it, so leftovers
    # from earlier runs would be reinstalled (and the wrong file name reported).
    $tempDir = Join-Path $env:TEMP "libupdate-$lib"
    if (Test-Path $tempDir) { Remove-Item -Recurse -Force -Path $tempDir }
    New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
    gh release download $targetTag -R "BROTLib/$lib" -p "*.library" -D $tempDir --clobber

    $libFile = Get-ChildItem -Path $tempDir -Filter "*.library" | Select-Object -First 1
    if (-not $libFile) {
        Write-Warning "  No .library asset found on release $targetTag for $lib -- skipping"
        continue
    }

    # RepTool.exe installs every .library file found in the given directory
    # (recursively), independent of any project/source -- this is what the
    # TwinCAT installer itself uses internally for the same purpose, and what
    # the community "snappy" CLI tool wraps for the exact same use case.
    #
    # Invoked via cmd.exe rather than PowerShell's & operator: PowerShell's own
    # argument marshalling mangles --profile values containing spaces (every
    # real TwinCAT profile name has spaces) into something RepTool rejects as
    # "No profile name specified", confirmed by isolated testing. cmd.exe passes
    # the same quoted string through correctly.
    $repToolCmd = "`"$RepTool`" --profile=`"$TcProfile`" --installLibsRecurs `"$tempDir`""
    cmd.exe /c $repToolCmd
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  Installed $($libFile.Name) ($targetVersion)" -ForegroundColor Green
    } else {
        Write-Warning "  RepTool exited $LASTEXITCODE installing $($libFile.Name) -- check output above"
    }
}
