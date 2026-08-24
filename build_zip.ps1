# Build the installable add-on zip: dist/arche_extensions-<version>.zip
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$init = Get-Content "arche_extensions/__init__.py" -Raw
if ($init -notmatch '"version":\s*\((\d+),\s*(\d+),\s*(\d+)\)') {
    throw "could not read version from arche_extensions/__init__.py"
}
$ver = "$($Matches[1]).$($Matches[2]).$($Matches[3])"

Get-ChildItem -Path "arche_extensions" -Filter "__pycache__" -Recurse -Directory |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

$out = "dist/arche_extensions-$ver.zip"
Remove-Item -Recurse -Force "dist" -ErrorAction SilentlyContinue
New-Item -ItemType Directory "dist" | Out-Null

# the archive must contain the package FOLDER, so Blender installs it as a package
Compress-Archive -Path "arche_extensions" -DestinationPath $out -CompressionLevel Optimal
Write-Output "built $out"
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead((Resolve-Path $out))
$zip.Entries | ForEach-Object { "  $($_.FullName)" }
$zip.Dispose()
