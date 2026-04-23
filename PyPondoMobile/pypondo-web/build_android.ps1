$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptDir

Write-Host "[1/4] Checking toolchain..."
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Error "npm not found. Install Node.js and ensure npm is on PATH."
    exit 1
}
if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
    Write-Error "java not found. Install JDK 11 or newer and ensure java is on PATH."
    exit 1
}

$nodeVersion = & node -v 2>&1 | Out-String
$npmVersion = & npm -v 2>&1 | Out-String
$javaVersionText = & java -version 2>&1 | Out-String
Write-Host "Detected Node: $nodeVersion".Trim()
Write-Host "Detected npm: $npmVersion".Trim()
Write-Host "Detected Java: $javaVersionText".Trim()

if ($javaVersionText -match 'version "1\.8') {
    Write-Error "Java 8 detected. JDK 11 or newer is required."
    exit 1
}

if (-not (Test-Path "node_modules")) {
    Write-Host "[2/4] Installing npm dependencies..."
    npm install
    if ($LASTEXITCODE -ne 0) {
        Write-Error "npm install failed."
        exit $LASTEXITCODE
    }
}

Write-Host "[3/4] Building web assets..."
npm run build
if ($LASTEXITCODE -ne 0) {
    Write-Error "Web build failed."
    exit $LASTEXITCODE
}

Write-Host "[4/4] Building Android APK..."
Push-Location "android"
& .\gradlew.bat assembleDebug
$gradleExit = $LASTEXITCODE
Pop-Location
if ($gradleExit -ne 0) {
    Write-Error "Android Gradle build failed."
    exit $gradleExit
}

$apkSource = Join-Path $scriptDir "android\app\build\outputs\apk\debug\app-debug.apk"
if (-not (Test-Path $apkSource)) {
    Write-Error "APK not found at $apkSource"
    exit 1
}

$destDir = Join-Path $scriptDir "..\..\PythonProject\bin"
if (-not (Test-Path $destDir)) {
    New-Item -ItemType Directory -Path $destDir | Out-Null
}

$destApk = Join-Path $destDir "pypondo_mobile-1.0.0-debug.apk"
Copy-Item -Path $apkSource -Destination $destApk -Force
Write-Host "SUCCESS: APK generated and copied to '$destApk'"
Write-Host "The APK uses the CyberCore icon and is configured for local network connections."
