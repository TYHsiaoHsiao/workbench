param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommandArgs
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
& python (Join-Path $Root "workbench.py") @CommandArgs
exit $LASTEXITCODE
