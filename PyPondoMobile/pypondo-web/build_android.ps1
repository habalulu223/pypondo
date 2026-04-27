$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptDir

function Resolve-JavaHome {
    $candidates = @()

    if ($env:JAVA_HOME) {
        $candidates += $env:JAVA_HOME
    }

    $candidates += @(
        'C:\Program Files\Android\Android Studio\jbr',
        'C:\Program Files\Android\Android Studio\jre'
    )

    $candidates += Get-ChildItem 'C:\Program Files\Java' -Directory -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty FullName
    $candidates += Get-ChildItem 'C:\Program Files\ojdkbuild' -Directory -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty FullName
    $candidates += Get-ChildItem 'C:\Program Files\Eclipse Adoptium' -Directory -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty FullName
    $candidates += Get-ChildItem 'C:\Program Files\Microsoft' -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like 'jdk*' } |
        Select-Object -ExpandProperty FullName

    foreach ($candidate in ($candidates | Where-Object { $_ } | Select-Object -Unique)) {
        $javaExe = Join-Path $candidate 'bin\java.exe'
        if (-not (Test-Path $javaExe)) {
            continue
        }

        $javaLine = & $javaExe -version 2>&1 | Select-Object -First 1
        if ($javaLine -and $javaLine -notmatch 'version "1\.') {
            return $candidate
        }
    }

    return $null
}

function Resolve-AndroidSdk {
    if ($env:ANDROID_HOME -and (Test-Path (Join-Path $env:ANDROID_HOME 'platform-tools'))) {
        return $env:ANDROID_HOME
    }

    if ($env:ANDROID_SDK_ROOT -and (Test-Path (Join-Path $env:ANDROID_SDK_ROOT 'platform-tools'))) {
        return $env:ANDROID_SDK_ROOT
    }

    $defaultSdk = Join-Path $env:LOCALAPPDATA 'Android\Sdk'
    if (Test-Path (Join-Path $defaultSdk 'platform-tools')) {
        return $defaultSdk
    }

    return $null
}

Write-Host "[1/6] Resolving Java toolchain..."
$javaHome = Resolve-JavaHome
if (-not $javaHome) {
    Write-Error "JDK 11 or newer was not found. Install JDK 17+ or Android Studio, then set JAVA_HOME."
    if (Get-Command java -ErrorAction SilentlyContinue) {
        & java -version
    }
    exit 1
}

$env:JAVA_HOME = $javaHome
$env:PATH = "$javaHome\bin;$env:PATH"
Write-Host "Using Java from $javaHome"
& java -version

Write-Host "[2/6] Resolving Android SDK..."
$androidSdk = Resolve-AndroidSdk
if (-not $androidSdk) {
    Write-Error "Android SDK not found. Install the Android SDK command-line tools or Android Studio, then make sure $env:LOCALAPPDATA\Android\Sdk exists."
    exit 1
}

$env:ANDROID_HOME = $androidSdk
$env:ANDROID_SDK_ROOT = $androidSdk
Set-Content -Path (Join-Path $scriptDir 'android\local.properties') -Value "sdk.dir=$($androidSdk -replace '\\', '\\')"
Write-Host "Using Android SDK at $androidSdk"

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Error "npm not found. Install Node.js and ensure npm is on PATH."
    exit 1
}

if (-not (Test-Path "node_modules")) {
    Write-Host "[3/6] Installing npm dependencies..."
    npm install
    if ($LASTEXITCODE -ne 0) {
        Write-Error "npm install failed."
        exit $LASTEXITCODE
    }
}
else {
    Write-Host "[3/6] npm dependencies already installed."
}

Write-Host "[4/6] Building bundled web assets..."
npm run build
if ($LASTEXITCODE -ne 0) {
    Write-Error "Web build failed."
    exit $LASTEXITCODE
}

Write-Host "[5/6] Syncing Capacitor Android project..."
npx cap sync android
if ($LASTEXITCODE -ne 0) {
    Write-Error "Capacitor Android sync failed."
    exit $LASTEXITCODE
}

Write-Host "Adjusting generated Gradle Java compatibility for the local JDK..."
$gradleFiles = @(
    (Join-Path $scriptDir 'android\app\capacitor.build.gradle'),
    (Join-Path $scriptDir 'android\capacitor-cordova-android-plugins\build.gradle'),
    (Join-Path $scriptDir 'node_modules\@capacitor\android\capacitor\build.gradle')
)
foreach ($gradleFile in $gradleFiles) {
    if (-not (Test-Path $gradleFile)) {
        continue
    }

    $content = Get-Content -Path $gradleFile -Raw
    $content = $content.Replace('JavaVersion.VERSION_21', 'JavaVersion.VERSION_17')
    Set-Content -Path $gradleFile -Value $content
}

if (-not (Test-Path "android\gradlew.bat")) {
    Write-Error "Android Gradle wrapper not found at $scriptDir\android\gradlew.bat"
    exit 1
}

Write-Host "[6/6] Building Android APK..."
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
Write-Host "[DONE] APK generated and copied to '$destApk'"
Write-Host "The APK bundles its own UI and connects directly to the PyPondo mobile API."
