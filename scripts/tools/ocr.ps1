# Windows built-in OCR (WinRT Windows.Media.Ocr) for IntelBureau.
# Usage: powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File ocr.ps1 -Path <image|dir> [-Lang zh-Hans-CN]
# When -Path is a directory, every *.png inside is recognized in name order (used for tiles of long screenshots).
# Output (stdout, UTF-8 JSON, one object):
#   {"ok":true,"lang":"zh-Hans-CN","max":10000,"items":[{"name":"000.png","width":..,"height":..,"lines":["..."]}]}
#   {"ok":false,"code":"too_large|no_engine|error","error":"...","max":10000}
# Read-only: never writes files, never touches the network.
param(
    [Parameter(Mandatory = $true)][string]$Path,
    [string]$Lang = "zh-Hans-CN"
)

$ErrorActionPreference = "Stop"

function Write-JsonOut($obj) {
    $json = $obj | ConvertTo-Json -Compress -Depth 5
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    $out = [Console]::OpenStandardOutput()
    $out.Write($bytes, 0, $bytes.Length)
    $out.Flush()
}

$maxDim = 0
try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
    $null = [Windows.Storage.FileAccessMode, Windows.Storage, ContentType = WindowsRuntime]
    $null = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
    $null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
    $null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics, ContentType = WindowsRuntime]
    $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
    $null = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType = WindowsRuntime]
    $null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]

    # Generic WindowsRuntimeSystemExtensions.AsTask<TResult>(IAsyncOperation<TResult>)
    $script:asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
            $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
            $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
        })[0]

    function Wait-WinRt($op, [Type]$resultType) {
        $task = $script:asTaskGeneric.MakeGenericMethod($resultType).Invoke($null, @($op))
        $null = $task.Wait(-1)
        return $task.Result
    }

    $maxDim = [int][Windows.Media.Ocr.OcrEngine]::MaxImageDimension
    $engine = $null
    try {
        $language = New-Object Windows.Globalization.Language($Lang)
        if ([Windows.Media.Ocr.OcrEngine]::IsLanguageSupported($language)) {
            $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
        }
    } catch {
        $engine = $null
    }
    if ($null -eq $engine) {
        $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    }
    if ($null -eq $engine) {
        Write-JsonOut @{ ok = $false; code = "no_engine"; error = "no OCR recognizer installed for $Lang"; max = $maxDim }
        exit 2
    }

    if (Test-Path -LiteralPath $Path -PathType Container) {
        $files = @(Get-ChildItem -LiteralPath $Path -Filter *.png | Sort-Object Name)
    } else {
        $files = @(Get-Item -LiteralPath $Path)
    }

    $items = @()
    foreach ($f in $files) {
        $storageFile = Wait-WinRt ([Windows.Storage.StorageFile]::GetFileFromPathAsync($f.FullName)) ([Windows.Storage.StorageFile])
        $stream = Wait-WinRt ($storageFile.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        try {
            $decoder = Wait-WinRt ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
            $bitmap = Wait-WinRt ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
            if ($bitmap.PixelWidth -gt $maxDim -or $bitmap.PixelHeight -gt $maxDim) {
                Write-JsonOut @{ ok = $false; code = "too_large"; error = "image exceeds OcrEngine.MaxImageDimension"; max = $maxDim }
                exit 3
            }
            $result = Wait-WinRt ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
            $lines = @()
            foreach ($line in $result.Lines) { $lines += [string]$line.Text }
            $items += , @{ name = $f.Name; width = $bitmap.PixelWidth; height = $bitmap.PixelHeight; lines = $lines }
        } finally {
            $stream.Dispose()
        }
    }
    Write-JsonOut @{ ok = $true; lang = $engine.RecognizerLanguage.LanguageTag; max = $maxDim; items = $items }
    exit 0
} catch {
    Write-JsonOut @{ ok = $false; code = "error"; error = $_.Exception.Message; max = $maxDim }
    exit 1
}
