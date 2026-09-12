[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('local', 'production')]
    [string] $Mode,
    [Parameter(Mandatory = $true)]
    [string] $RepositoryRoot,
    [string] $JavaPath,
    [string] $ExpectedUsername,
    [string] $StateRoot
)

$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
    throw 'LOCALAPPDATA 未设置，无法定位 Operator 配置。'
}
$repository = (Resolve-Path -LiteralPath $RepositoryRoot).Path
if ([string]::IsNullOrWhiteSpace($StateRoot)) {
    $StateRoot = Join-Path $env:LOCALAPPDATA $(if ($Mode -eq 'local') {
            'InkForge\codex-operator'
        } else {
            'InkForge\production-codex-operator'
        })
}
if ([string]::IsNullOrWhiteSpace($JavaPath)) {
    $javaCommand = Get-Command java.exe -ErrorAction SilentlyContinue
    if ($null -eq $javaCommand) {
        throw '未找到 Java 21，请提供 -JavaPath。'
    }
    $JavaPath = $javaCommand.Source
} else {
    $JavaPath = (Resolve-Path -LiteralPath $JavaPath).Path
}
if (-not (Test-Path -LiteralPath $JavaPath -PathType Leaf)) {
    throw 'Java executable 不存在。'
}

$jarPath = Join-Path $repository 'tools\inkforge-cli-java\target\inkforge-cli.jar'
if (-not (Test-Path -LiteralPath $jarPath -PathType Leaf)) {
    throw '未找到已构建的 inkforge-cli.jar；请先按 CLI 文档构建。'
}

$javaArguments = @(
    '-cp', $jarPath,
    'cn.inkforge.cli.operator.OperatorMain',
    $Mode, '--authorization-profile', 'windows-v1', 'configure',
    '--repository-root', $repository,
    '--state-root', $StateRoot
)
if (-not [string]::IsNullOrWhiteSpace($ExpectedUsername)) {
    $javaArguments += @('--expected-username', $ExpectedUsername)
}

# configure 只安装固定 JAR 和非秘密配置，令牌仍由 Java 写入 Windows Credential Manager。
& $JavaPath @javaArguments
exit $LASTEXITCODE
