# instalar.ps1: creates the dedicated WSL2 distro "tune-up". All logic lives in etapas.psm1.
# Run as the normal user (never elevated): only the System32 wsl.exe is elevated, when needed.
# Source is UTF-8 with BOM so Windows PowerShell 5.1 reads the pt-BR accents correctly.
[CmdletBinding()]
param(
    [switch]$Retomar,
    [switch]$Remover,
    [switch]$Login,
    [switch]$Atualizar,
    [switch]$Medir,
    [string]$Projeto,
    [switch]$SemReiniciar,
    [switch]$Forcar
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'etapas.psm1') -Force
$codigo = Invoke-Instalador -Retomar:$Retomar -Remover:$Remover -Login:$Login -Atualizar:$Atualizar -Medir:$Medir `
    -Projeto $Projeto -SemReiniciar:$SemReiniciar -Forcar:$Forcar -Script $PSCommandPath
exit $codigo
