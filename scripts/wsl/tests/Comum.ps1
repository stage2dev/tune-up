# Shared helpers for the instalar.ps1 Pester tests: a fake Windows machine behind the etapas.psm1 wrappers.
# State lives in $global:TU so mock bodies (which run outside the module) can read and change it.
$RaizWsl = Split-Path -Parent $PSScriptRoot
Import-Module (Join-Path $RaizWsl 'etapas.psm1') -Force
$EhWindows = ($PSVersionTable.PSEdition -eq 'Desktop') -or ((Test-Path variable:IsWindows) -and $IsWindows)
$RaizRepoReal = Split-Path -Parent (Split-Path -Parent $RaizWsl)
$VersaoPluginReal = ([IO.File]::ReadAllText((Join-Path (Join-Path $RaizRepoReal '.claude-plugin') 'plugin.json')) | ConvertFrom-Json).version
$NodeVersaoReal = ([regex]::Match([IO.File]::ReadAllText((Join-Path $RaizWsl 'fixados.env')), '(?m)^NODE_VERSAO=(\S+)')).Groups[1].Value

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
        Ancoras = New-Object System.Collections.ArrayList
        Admin = $false; ListaCodigo = 0; Terminais = New-Object System.Collections.ArrayList; TerminalAbre = $true; LoginEm = $null
        # Fake distro: Conf = wsl.conf on disk ('on' = interop on), Interop = what the running distro has.
        D = @{ Raiz = $false; Padrao = 'root'; Conf = 'on'; Interop = $true; Plugin = ''; Claude = $false; Auth = $true
            MedirCodigo = 0; BgCodigo = 0; M9Mutilar = $false; MedirSaida = ''; Sessao = 'ok'; Marca = $false; Codigos = @{}; TesteClaude = $null; AgentsCodigo = 0; AgentsSaida = ''; Verificar = 'RELATORIO-VERIFICAR'
            Parcial = $false }   # Parcial: a half-failed --usuario left --verificar failing
    }
}

# Answers every `wsl.exe -d tune-up [-u x] --exec ...` call from the fake distro state.
function Invoke-DistroFalsa {
    param([string[]]$Argv)
    $D = $global:TU.D
    $i = [array]::IndexOf($Argv, '--exec')
    $cmd = $Argv[($i + 1)..($Argv.Count - 1)] -join ' '
    $r = @{ Codigo = 0; Saida = '' }
    $modo = $null
    if ($cmd -like '/bin/bash /usr/local/lib/tune-up/preparar.sh *') {
        $modo = $Argv[$i + 3]
        if ($D.Codigos.ContainsKey($modo)) { $r.Codigo = $D.Codigos[$modo] }
        if ($modo -eq '--verificar') { $r.Saida = $D.Verificar; if ($D.Parcial) { $r.Codigo = 1 } }   # the report prints on success and failure
    }
    # -Medir: printf echoes its text, medir.sh answers from D.MedirSaida, claude --bg prints a session id.
    if ($Argv[$i + 1] -eq '/usr/bin/printf') { $r.Saida = $Argv[$i + 3] }
    if ($cmd -like '/bin/bash /usr/local/lib/tune-up/medir.sh *') { $r.Codigo = $D.MedirCodigo; $r.Saida = $D.MedirSaida }
    if ($cmd -like '/usr/local/bin/tune-up-exec * --bg *') { $r.Saida = 'backgrounded ' + [char]0xB7 + ' abc123def'; $r.Codigo = $D.BgCodigo }
    # M9 byte check: python prints the hex of its argument bytes; M9Mutilar fakes a console that turned non-ASCII into '?'.
    if ($Argv[$i + 1] -eq '/usr/bin/python3') {
        $txt = $Argv[-1]; if ($D.M9Mutilar) { $txt = $txt -replace '[^\x00-\x7f]', '?' }
        $r.Saida = (([Text.UTF8Encoding]::new($false)).GetBytes($txt) | ForEach-Object { '{0:x2}' -f $_ }) -join ''
    }
    switch -Exact ($cmd) {
        '/usr/bin/test -x /usr/local/bin/tune-up-exec' { if (-not $D.Raiz) { $r.Codigo = 1 } }
        '/usr/local/bin/node --version' { if ($D.Raiz) { $r.Saida = "v$NodeVersaoReal" } else { $r.Codigo = 127 } }
        '/usr/bin/id -un' { $r.Saida = $D.Padrao }
        '/bin/rm -f /etc/tune-up/pronto.json' { $D.Marca = $false }
        '/usr/bin/test -x /home/tuneup/.local/bin/claude' {
            if ($null -ne $D.TesteClaude) { $r.Codigo = $D.TesteClaude } elseif (-not $D.Claude) { $r.Codigo = 1 }
        }
        '/usr/bin/test -d /home/tuneup' { if (-not $D.Raiz) { $r.Codigo = 1 } }
        '/home/tuneup/.local/bin/claude agents --json --all' { $r.Codigo = $D.AgentsCodigo; $r.Saida = $D.AgentsSaida }
        '/home/tuneup/.local/bin/claude auth status' { $r.Saida = 'SEGREDO-AUTH pessoa@exemplo.com'; if (-not $D.Auth) { $r.Codigo = 1 } }
        '/usr/bin/test -f /etc/tune-up/pronto.json' { if (-not $D.Marca) { $r.Codigo = 1 } }
        '/usr/bin/printenv WSL_INTEROP' { if ($D.Interop) { $r.Saida = '/run/WSL/1_interop' } else { $r.Codigo = 1 } }
    }
    if ($modo -and $r.Codigo -eq 0) {
        switch ($modo) {
            '--raiz' { $D.Raiz = $true; $D.Conf = 'on'; $D.Marca = $false }
            '--usuario' { $D.Plugin = $VersaoPluginReal; $D.Claude = $true; $D.Parcial = $false }
            '--versao-plugin' { if ($D.Plugin) { $r.Saida = $D.Plugin } else { $r.Codigo = 1 } }
            '--fechar' { $D.Conf = 'off' }
            '--abrir-interop' { $D.Marca = $false; $D.Conf = 'on' }
            '--marcar' { if ($D.Interop) { $r.Codigo = 7 } else { $D.Marca = $true } }
        }
    }
    [pscustomobject]$r
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
        if ($Argv[0] -eq '-d') { return (Invoke-DistroFalsa $Argv) }
        $r = @{ Codigo = 0; Saida = '' }
        switch -Wildcard ($Argv -join ' ') {
            '--terminate *' { $global:TU.D.Interop = ($global:TU.D.Conf -eq 'on'); if ($global:TU.D.Raiz) { $global:TU.D.Padrao = 'tuneup' } }
            '--unregister *' { $global:TU.Distros = @($global:TU.Distros | Where-Object { $_ -ne $Argv[1] }); $global:TU.Reg = $null }
            '--version' { if (-not $global:TU.Wsl) { $r.Codigo = 1 } else { $r.Saida = "Versão do WSL: 2.4.0.0`nVersão do kernel: 5.15.153.1" } }
            '-l -q' { $r.Saida = ($global:TU.Distros -join "`n"); if ($global:TU.ListaCodigo) { $r.Codigo = $global:TU.ListaCodigo } }
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
    Mock -ModuleName etapas Test-Administrador { $global:TU.Admin }
    Mock -ModuleName etapas Get-CaminhoWsl { 'C:\Windows\System32\wsl.exe' }
    Mock -ModuleName etapas Start-Terminal { $null = $global:TU.Terminais.Add([string[]]$Argv); $global:TU.TerminalAbre }
    Mock -ModuleName etapas Wait-Segundos {
        $global:TU.Agora += $Segundos
        if ($global:TU.LoginEm -and $global:TU.Agora -ge $global:TU.LoginEm) { $global:TU.D.Auth = $true }
    }
    # The repo root of a Linux test run is not a drive-letter path; ConvertTo-CaminhoWsl has its own tests.
    Mock -ModuleName etapas Start-Ancora { $null = $global:TU.Ancoras.Add('start'); [pscustomobject]@{ Id = 4242 } }
    Mock -ModuleName etapas Stop-Ancora { if ($Processo) { $null = $global:TU.Ancoras.Add('stop') } }
    Mock -ModuleName etapas Get-RaizRepoWsl { '/mnt/c/tune-up' }
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
    $globais = '--import', '--set-version', '--update', '--install', '--unregister', '--terminate'
    $dentro = '/usr/bin/install', '/bin/rm', '--raiz', '--usuario', '--fechar', '--marcar', '--abrir-interop'
    foreach ($a in $global:TU.Argvs) {
        if ($a[0] -in $globais -or @($a | Where-Object { $_ -in $dentro }).Count -gt 0) { , $a }
    }
}

# argv of in-distro calls only, joined with '|', in call order.
function Get-ChamadasDistro { @($global:TU.Argvs | Where-Object { $_[0] -eq '-d' -or $_[0] -in '--terminate', '--unregister' } | ForEach-Object { $_ -join '|' }) }
