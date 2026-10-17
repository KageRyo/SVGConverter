param(
    [Parameter(Mandatory = $true)]
    [string]$Executable
)

$ErrorActionPreference = "Stop"
$executablePath = (Resolve-Path -LiteralPath $Executable).Path
$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("svgconverter-smoke-" + [guid]::NewGuid())
$originalPath = $env:PATH
$originalPythonPath = $env:PYTHONPATH
$originalPythonHome = $env:PYTHONHOME

function Invoke-Conversion([string]$Source, [string]$Output, [string]$Mode, [switch]$Preview) {
    $prefix = if ($Preview) { "--preview" } else { "--cli" }
    $process = Start-Process -FilePath $executablePath -ArgumentList @(
        $prefix, "`"$Source`"", "--output", "`"$Output`"", "--mode", $Mode
    ) -PassThru
    # Retain the handle so ExitCode remains available after the process ends.
    $null = $process.Handle
    if (-not $process.WaitForExit(60000)) {
        $process.Kill($true)
        throw "The packaged $Mode conversion timed out."
    }
    return $process.ExitCode
}

try {
    $null = New-Item -ItemType Directory -Path $testRoot
    $inputPath = Join-Path $testRoot "logo spaces 漢字.png"
    Add-Type -AssemblyName System.Drawing
    $bitmap = [System.Drawing.Bitmap]::new(32, 32)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.Clear([System.Drawing.Color]::White)
        $graphics.FillRectangle([System.Drawing.Brushes]::Black, 8, 8, 16, 16)
        $bitmap.Save($inputPath, [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }

    # The frozen application must not find Python or VTracer in the build environment.
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    $env:PYTHONPATH = $null
    $env:PYTHONHOME = $null
    $sourceHash = (Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash
    $finalSvg = [System.IO.Path]::ChangeExtension($inputPath, ".svg")
    [System.IO.File]::WriteAllText($finalSvg, "Preserve this existing SVG.")
    foreach ($mode in @("embed", "vectorize")) {
        $outputPath = Join-Path $testRoot "$mode.svg"
        $exitCode = Invoke-Conversion $inputPath $outputPath $mode
        if ($exitCode -ne 0) {
            throw "The packaged $mode conversion exited with code $exitCode."
        }
        if (-not (Test-Path -LiteralPath $outputPath -PathType Leaf)) {
            throw "The packaged $mode conversion did not create an SVG."
        }
        [xml]$document = Get-Content -Raw -LiteralPath $outputPath
        if ($document.DocumentElement.LocalName -ne "svg" -or
            $document.DocumentElement.NamespaceURI -ne "http://www.w3.org/2000/svg") {
            throw "The packaged $mode conversion did not create a valid SVG root."
        }
        $namespaces = [System.Xml.XmlNamespaceManager]::new($document.NameTable)
        $namespaces.AddNamespace("svg", "http://www.w3.org/2000/svg")
        $images = $document.SelectNodes("//svg:image", $namespaces)
        $paths = $document.SelectNodes("//svg:path", $namespaces)
        if ($mode -eq "embed" -and $images.Count -lt 1) {
            throw "The packaged Embed conversion did not embed the raster."
        }
        if ($mode -eq "vectorize" -and ($paths.Count -lt 1 -or $images.Count -ne 0)) {
            throw "The packaged Vectorize conversion must contain paths without raster images."
        }
        Write-Host "Packaged $mode conversion passed ($((Get-Item -LiteralPath $outputPath).Length) bytes)."
        $previewPath = Join-Path $testRoot "$mode-preview.png"
        $previewExitCode = Invoke-Conversion $inputPath $previewPath $mode -Preview
        if ($previewExitCode -ne 0 -or -not (Test-Path -LiteralPath $previewPath -PathType Leaf)) {
            throw "The packaged $mode process preview failed (exit $previewExitCode)."
        }
        $preview = [System.Drawing.Bitmap]::FromFile($previewPath)
        try {
            if ($preview.RawFormat.Guid -ne [System.Drawing.Imaging.ImageFormat]::Png.Guid -or
                $preview.Width -ne 32 -or $preview.Height -ne 32) {
                throw "The packaged $mode process preview is not the expected PNG."
            }
            $center = $preview.GetPixel(16, 16)
            if ($center.A -ne 255 -or $center.R -gt 32 -or $center.G -gt 32 -or $center.B -gt 32) {
                throw "The packaged $mode preview did not render the black logo."
            }
        }
        finally {
            $preview.Dispose()
        }
        $previewHash = (Get-FileHash -LiteralPath $previewPath -Algorithm SHA256).Hash
        if ((Invoke-Conversion $inputPath $previewPath $mode -Preview) -ne 1 -or
            (Get-FileHash -LiteralPath $previewPath -Algorithm SHA256).Hash -ne $previewHash) {
            throw "The packaged preview replaced an existing PNG."
        }
        if ([System.IO.File]::ReadAllText($finalSvg) -ne "Preserve this existing SVG." -or
            (Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash -ne $sourceHash) {
            throw "The packaged preview modified the source or an existing SVG."
        }
        Write-Host "Packaged $mode spawned preview passed."
    }
    $invalidPath = Join-Path $testRoot "invalid.png"
    Set-Content -LiteralPath $invalidPath -Value "This is not a PNG."
    $failureOutput = Join-Path $testRoot "failure.svg"
    if ((Invoke-Conversion $invalidPath $failureOutput "embed") -ne 1 -or
        (Test-Path -LiteralPath $failureOutput)) {
        throw "The packaged CLI did not preserve conversion failure behavior."
    }
}
finally {
    $env:PATH = $originalPath
    $env:PYTHONPATH = $originalPythonPath
    $env:PYTHONHOME = $originalPythonHome
    Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
}
