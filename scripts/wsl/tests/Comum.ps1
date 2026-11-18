# Shared helpers for the instalar.ps1 Pester tests: a fake Windows machine behind the etapas.psm1 wrappers.
# State lives in $global:TU so mock bodies (which run outside the module) can read and change it.
$RaizWsl = Split-Path -Parent $PSScriptRoot
Import-Module (Join-Path $RaizWsl 'etapas.psm1') -Force
$EhWindows = ($PSVersionTable.PSEdition -eq 'Desktop') -or ((Test-Path variable:IsWindows) -and $IsWindows)

function Get-Sha256Texto {
    param([string]$Texto)
    $sha = [Security.Cryptography.SHA256]::Create()
    -join ($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Texto)) | ForEach-Object { $_.ToString('x2') })
}

# Copy of the real fixados.env with UBUNTU_SHA256 pointing at the fake download content.
function New-FixadosTeste {
    param([string]$Destino)
    $sha = Get-Sha256Texto 'conteudo-ubuntu'
    $linhas = [IO.File]::ReadAllText((Join-Path $RaizWsl 'fixados.env')).Split("`n") | ForEach-Object {
        if ($_.StartsWith('UBUNTU_SHA256=')) { "UBUNTU_SHA256=$sha" } else { $_ }
    }
    [IO.File]::WriteAllText($Destino, ($linhas -join "`n"), (New-Object Text.UTF8Encoding $false))
    return $Destino
}

function New-Maquina {
    & (Get-Module etapas) { $script:ArquivoLog = $null }   # a previous block's TestDrive is gone
    $global:TU = @{
        Build = 22631; Arch = 9; Hyper = $true; VirtFw = $true; Livre = 50GB; TipoDisco = 3
        Wsl = $true; InstalarLiga = $true; ElevadoCodigo = 0; UpdateCodigo = 0; UpdateSaida = ''
        Distros = @(); Reg = $null; ImportCodigo = 0; ImportSaida = ''; Versao = '2'
        Hklm = $false; Boot = 100; Agora = 1000; Resposta = 'n'; Conteudo = 'conteudo-ubuntu'
        Argvs = New-Object System.Collections.ArrayList
        Elevados = New-Object System.Collections.ArrayList
        Msgs = New-Object System.Collections.ArrayList
        RunOnce = $null
    }
}

# Every wrapper with an external effect is mocked here; call from BeforeEach.
function Use-MaquinaFalsa {
    Mock -ModuleName etapas Write-Mensagem { $null = $global:TU.Msgs.Add($Texto) }
    Mock -ModuleName etapas Get-InfoWindows { @{ Build = $global:TU.Build; SO64 = $true; Processo64 = $true } }
    Mock -ModuleName etapas Get-InfoSistema {
        switch ($Classe) {
            'Win32_Processor' { [pscustomobject]@{ Architecture = $global:TU.Arch; VirtualizationFirmwareEnabled = $global:TU.VirtFw } }
            'Win32_ComputerSystem' { [pscustomobject]@{ HypervisorPresent = $global:TU.Hyper } }
            'Win32_LogicalDisk' { [pscustomobject]@{ FreeSpace = $global:TU.Livre; DriveType = $global:TU.TipoDisco } }
        }
    }
    Mock -ModuleName etapas Invoke-Wsl {
        $null = $global:TU.Argvs.Add([string[]]$Argv)
        $r = @{ Codigo = 0; Saida = '' }
        switch -Wildcard ($Argv -join ' ') {
            '--version' { if (-not $global:TU.Wsl) { $r.Codigo = 1 } }
            '-l -q' { $r.Saida = ($global:TU.Distros -join "`n") }
            '-l -v' { $r.Saida = "  NAME      STATE           VERSION`n* tune-up    Stopped         $($global:TU.Versao)" }
            '--update' { $r.Codigo = $global:TU.UpdateCodigo; $r.Saida = $global:TU.UpdateSaida }
            '--import *' {
                $r.Codigo = $global:TU.ImportCodigo; $r.Saida = $global:TU.ImportSaida
                if ($r.Codigo -eq 0) {
                    $global:TU.Distros += 'tune-up'
                    $global:TU.Reg = [pscustomobject]@{ Guid = '{1111-2222}'; BasePath = $Argv[2] }
                }
            }
        }
        [pscustomobject]$r
    }
    Mock -ModuleName etapas Invoke-WslElevado {
        $null = $global:TU.Argvs.Add([string[]]$Argv)
        $null = $global:TU.Elevados.Add($Argv -join ' ')
        if ($Argv[0] -eq '--install' -and $global:TU.InstalarLiga) { $global:TU.Wsl = $true }
        $global:TU.ElevadoCodigo
    }
    Mock -ModuleName etapas Invoke-Download { [IO.File]::WriteAllText($Destino, $global:TU.Conteudo) }
    Mock -ModuleName etapas Get-DistroRegistrada { $global:TU.Reg }
    Mock -ModuleName etapas Test-ReinicioPendenteHklm { $global:TU.Hklm }
    Mock -ModuleName etapas Set-RunOnce { $global:TU.RunOnce = $Comando }
    Mock -ModuleName etapas Remove-RunOnce { $global:TU.RunOnce = $null }
    Mock -ModuleName etapas Read-Resposta { $global:TU.Resposta }
    Mock -ModuleName etapas Invoke-ReiniciarWindows { }
    Mock -ModuleName etapas Get-UltimoBoot { $global:TU.Boot }
    Mock -ModuleName etapas Get-Agora { $global:TU.Agora }
}

# Runs the installer against a fresh LOCALAPPDATA under TestDrive unless -MesmaPasta.
function Invoke-InstaladorTeste {
    param([hashtable]$Extra = @{}, [switch]$MesmaPasta)
    if (-not $MesmaPasta) { $env:LOCALAPPDATA = Join-Path $TestDrive ([guid]::NewGuid().ToString('N')) }
    $fx = New-FixadosTeste (Join-Path $TestDrive 'fixados.env')
    $global:TU.Msgs.Clear()
    Invoke-Instalador -Fixados $fx -Script 'C:\tune-up\scripts\wsl\instalar.ps1' @Extra
}

function Get-PastaTeste { Join-Path (Join-Path $env:LOCALAPPDATA 'tune-up') 'wsl' }

function Get-ArgvsDeEscrita {
    @($global:TU.Argvs | Where-Object { $_[0] -in '--import', '--set-version', '--update', '--install', '--unregister' })
}
