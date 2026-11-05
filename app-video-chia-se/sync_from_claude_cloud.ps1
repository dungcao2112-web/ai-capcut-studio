param(
    [string]$RepoUrl = "https://github.com/dungcao2112-web/app-video-chia-se.git",
    [string]$Branch = ""
)

$ErrorActionPreference = "Continue"
Set-Location "E:\vd chia se"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  DONG BO CODE TOI UU TU CLAUDE CLOUD VE MAY (E:\vd chia se)" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$currentRemote = git remote get-url origin 2>$null
if (-not $currentRemote) {
    git remote add origin $RepoUrl
} elseif ($currentRemote -ne $RepoUrl) {
    git remote set-url origin $RepoUrl
}

Write-Host "[1/3] Dang tai cac nhanh moi nhat tu GitHub ($RepoUrl)..." -ForegroundColor Yellow
git fetch origin --prune

if (-not $Branch) {
    # Tu dong tim nhanh claude/* moi nhat hoac origin/main
    $claudeBranch = git for-each-ref --sort=-committerdate refs/remotes/origin/claude/ --format="%(refname:short)" | Select-Object -First 1
    if ($claudeBranch) {
        $Branch = $claudeBranch
        Write-Host "-> Phat hien nhanh Claude Cloud moi nhat: $Branch" -ForegroundColor Green
    } else {
        $Branch = "origin/main"
        Write-Host "-> Su dung nhanh mac dinh: $Branch" -ForegroundColor Green
    }
}

Write-Host "[2/3] Dang gop (merge) code tu $Branch vao E:\vd chia se..." -ForegroundColor Yellow
git merge $Branch --allow-unrelated-histories --no-edit

if (Test-Path "E:\vd chia se\remotion\ConvoAppDynamic.tsx") {
    $remotionTarget = "C:\Users\Dung\Developer\remotion-starter\src\ConvoAppDynamic.tsx"
    if (Test-Path "C:\Users\Dung\Developer\remotion-starter\src") {
        Copy-Item "E:\vd chia se\remotion\ConvoAppDynamic.tsx" $remotionTarget -Force
        Write-Host "[3/3] Da dong bo ConvoAppDynamic.tsx sang Remotion ($remotionTarget)!" -ForegroundColor Green
    }
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  HOAN TAT! Code tu Claude Cloud da duoc cap nhat." -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
