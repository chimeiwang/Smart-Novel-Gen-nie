[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('local', 'production')]
    [string] $Mode,
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]] $CommandArguments,
    [Parameter(ValueFromPipeline = $true)]
    [AllowEmptyString()]
    [string] $OperatorInput
)

begin {
    $ErrorActionPreference = 'Stop'
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [Console]::InputEncoding = $utf8
    [Console]::OutputEncoding = $utf8
    $OutputEncoding = $utf8
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        throw 'LOCALAPPDATA 未设置，无法定位 Operator 配置。'
    }
    $stdinLines = New-Object System.Collections.Generic.List[string]
    $stateRoot = Join-Path $env:LOCALAPPDATA $(if ($Mode -eq 'local') {
            'InkForge\codex-operator'
        } else {
            'InkForge\production-codex-operator'
        })

    if ($CommandArguments.Count -ge 2 -and $CommandArguments[0] -eq '--state-root') {
        if ([string]::IsNullOrWhiteSpace($CommandArguments[1])) {
            throw '缺少 --state-root 路径。'
        }
        $stateRoot = $CommandArguments[1]
        $CommandArguments = @($CommandArguments | Select-Object -Skip 2)
    }

    $configPath = Join-Path $stateRoot 'config.json'
    $jarPath = Join-Path $stateRoot 'runtime\inkforge-cli.jar'
    if (-not (Test-Path -LiteralPath $configPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $jarPath -PathType Leaf)) {
        throw 'Java CLI 尚未配置，请先运行 configure.ps1。'
    }
    try {
        $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $javaPath = [string]$config.javaPath
        if ([string]::IsNullOrWhiteSpace($javaPath) -or
            -not [IO.Path]::IsPathRooted($javaPath) -or
            -not (Test-Path -LiteralPath $javaPath -PathType Leaf)) {
            throw 'javaPath 无效'
        }
    } catch {
        throw 'Operator 配置无效，请重新运行 configure.ps1。'
    }

    $javaArguments = @(
        '-cp', $jarPath,
        'cn.inkforge.cli.operator.OperatorMain',
        $Mode, '--authorization-profile', 'windows-v1',
        '--state-root', $stateRoot
    ) + @($CommandArguments)
}

process {
    if ($PSBoundParameters.ContainsKey('OperatorInput')) {
        $stdinLines.Add($OperatorInput)
    }
}

end {
    # 使用参数数组，保证 JSON、路径和 Unicode 不经过 shell 再解析。
    if ($stdinLines.Count -gt 0) {
        ($stdinLines -join [Environment]::NewLine) | & $javaPath @javaArguments
    } else {
        & $javaPath @javaArguments
    }
    exit $LASTEXITCODE
}
