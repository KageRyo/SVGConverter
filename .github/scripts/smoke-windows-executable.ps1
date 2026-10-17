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

function Invoke-Conversion([string]$Source, [string]$Output, [string]$Mode) {
    $process = Start-Process -FilePath $executablePath -ArgumentList @(
        "--cli", "`"$Source`"", "--output", "`"$Output`"", "--mode", $Mode
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
