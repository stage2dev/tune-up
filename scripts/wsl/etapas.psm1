# etapas.psm1: all logic of the tune-up WSL installer; instalar.ps1 is only the entry point.
# Every external effect goes through a small wrapper so Pester can Mock it and later steps reuse it:
# Invoke-Wsl, Invoke-WslElevado, Get-InfoSistema, Get-InfoWindows, Invoke-Download, the registry helpers,
# Read-Resposta, Invoke-ReiniciarWindows, Get-Agora and Get-UltimoBoot (all in apoio.ps1).
# Source is UTF-8 with BOM so Windows PowerShell 5.1 reads the pt-BR accents correctly.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Registry roots are injectable: tests point them at TestRegistry:. HKLM is only ever read (Test-Path).
$script:RaizHkcu = 'HKCU:'
$script:RaizHklm = 'HKLM:'
# Set by Fazer-E9 when -Projeto was given; Open-Projeto (distro.ps1) consumes it once the marker is written.
$script:ProjetoPendente = $false
$script:ChavesReinicioHklm = @(
    'SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending',
    'SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired')
$script:ChavesFixados = @('UBUNTU_URL', 'UBUNTU_SHA256', 'NODE_VERSAO', 'NODE_URL', 'NODE_SHA256',
    'FFMPEG_URL', 'FFMPEG_SHA256', 'CLAUDE_VERSAO', 'CLAUDE_URL', 'CLAUDE_SHA256',
    'CHROME_VERSAO', 'CHROME_URL', 'CHROME_SHA256', 'DISTRO', 'USUARIO')
# Step table. A step N is live when functions Testar-E<N> and Fazer-E<N> exist (7-10 live in distro.ps1).
$script:Etapas = @(
    @{ N = 1; Texto = 'Verificando o Windows' },
    @{ N = 2; Texto = 'Verificando se o WSL está instalado' },
    @{ N = 3; Texto = 'Verificando se o Windows precisa reiniciar' },
    @{ N = 4; Texto = 'Atualizando o WSL' },
    @{ N = 5; Texto = 'Baixando o Ubuntu' },
    @{ N = 6; Texto = 'Criando a distro tune-up' },
    @{ N = 7; Texto = 'Preparando o sistema da distro' },
    @{ N = 8; Texto = 'Instalando o Claude Code e o plugin' },
    @{ N = 9; Texto = 'Entrando na sua conta do Claude' },
    @{ N = 10; Texto = 'Conferindo tudo e fechando a ponte com o Windows' })
$script:Pasta = $null
$script:ArquivoLog = $null
$script:Fixados = $null
$script:Estado = $null
$script:EstadoExistia = $false
$script:EtapaAtual = 0
$script:PedidoReinicio = 0
$script:Aviso = $false
# Repo root (two levels above scripts\wsl): source of the files copied into the distro and of plugin.json.
$script:RaizRepo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$script:Opcoes = @{ Script = ''; Projeto = ''; SemReiniciar = $false; Forcar = $false; Retomar = $false }

# Wrappers and helpers live in apoio.ps1 (split for size); dot-sourced so they share this module scope.
. (Join-Path $PSScriptRoot 'apoio.ps1')
. (Join-Path $PSScriptRoot 'distro.ps1')
. (Join-Path $PSScriptRoot 'medir.ps1')

function Invoke-Reinicio {
    param([int]$Etapa)
    $script:Estado.etapa = $Etapa
    $script:Estado.reinicioPedidoEm = Get-Agora
    Save-Estado
    $cmd = Get-ComandoRetomar
    $caminhos = '{0}{1}' -f $script:Opcoes.Script, $script:Opcoes.Projeto
    if ($cmd.Length -le 260 -and -not $caminhos.Contains('"') -and -not $script:Opcoes.Projeto.EndsWith('\')) {
        Set-RunOnce -Comando $cmd
        Write-Mensagem 'O Windows precisa reiniciar. Depois que você entrar de novo, o instalador continua sozinho.'
    } else {
        Write-Mensagem 'O Windows precisa reiniciar. Depois que você entrar de novo, rode este comando no PowerShell:'
        Write-Mensagem $cmd
    }
    if ($script:Opcoes.SemReiniciar) {
        Write-Mensagem 'Reinicie o computador quando puder.'
        return 0
    }
    $r = Read-Resposta 'Reiniciar agora? (s/N)'
    if ("$r" -match '^\s*[sS]') { Invoke-ReiniciarWindows }
    return 0
}

function Initialize-Instalador {
    param([string]$Fixados)
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        Stop-Instalador 'A variável LOCALAPPDATA está vazia. Abra o PowerShell normalmente (sem ser como outro usuário) e tente de novo.' 2
    }
    if (-not $Fixados) { $Fixados = Join-Path $PSScriptRoot 'fixados.env' }
    $script:Fixados = Read-Fixados -Caminho $Fixados
    $script:ProjetoPendente = $false
    if ($script:Opcoes.Projeto) {
        $null = ConvertTo-CaminhoWsl -Caminho $script:Opcoes.Projeto
        if (-not (Test-Path -LiteralPath $script:Opcoes.Projeto -PathType Container)) {
            Stop-Instalador ('A pasta do projeto não existe: {0}' -f $script:Opcoes.Projeto) 2
        }
    }
    $script:Pasta = Join-Path (Join-Path $env:LOCALAPPDATA 'tune-up') 'wsl'
    foreach ($p in 'distro', 'baixados', 'logs') { $null = New-Item -ItemType Directory -Force -Path (Join-Path $script:Pasta $p) }
    $script:ArquivoLog = Join-Path (Join-Path $script:Pasta 'logs') ('instalar-{0}.log' -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
    Read-Estado
}

# E1 Windows: a read-only check that runs every time (it writes nothing).
function Testar-E1 { return $false }
function Fazer-E1 {
    $w = Get-InfoWindows
    if ($w.Build -lt 19041) {
        Stop-Instalador ('Este Windows é antigo demais (build {0}). O WSL 2 precisa do Windows 10 versão 2004 (build 19041) ou mais novo. Atualize o Windows e rode de novo.' -f $w.Build)
    }
    $cpu = @(Get-InfoSistema -Classe Win32_Processor)[0]
    if ($cpu.Architecture -ne 9 -or -not $w.SO64) {
        Stop-Instalador 'Este instalador só funciona no Windows de 64 bits com processador Intel ou AMD (x64). Computadores ARM64 e Windows de 32 bits não são suportados.'
    }
    if (-not $w.Processo64) { Stop-Instalador 'Abra o "Windows PowerShell" normal (64 bits), não o "(x86)", e rode de novo.' }
    $cs = @(Get-InfoSistema -Classe Win32_ComputerSystem)[0]
    if (-not $cs.HypervisorPresent -and $cpu.VirtualizationFirmwareEnabled -eq $false) {
        Stop-Instalador 'A virtualização está desligada. Reinicie o computador, entre na BIOS/UEFI (geralmente apertando F2, F10 ou Del ao ligar) e ative "Intel VT-x", "AMD-V" ou "SVM". Depois rode o instalador de novo.'
    }
    $unidade = [IO.Path]::GetPathRoot($script:Pasta).TrimEnd('\', '/')
    $disco = @(Get-InfoSistema -Classe Win32_LogicalDisk -Filtro ("DeviceID='{0}'" -f $unidade))
    if ($disco.Count -eq 0) { Stop-Instalador "Não consegui medir o espaço livre na unidade $unidade." }
    if ($disco[0].FreeSpace -lt 12GB) {
        Stop-Instalador ('Falta espaço: a unidade {0} tem {1:N1} GB livres e o tune-up precisa de 12 GB. Libere espaço e rode de novo.' -f $unidade, ($disco[0].FreeSpace / 1GB))
    }
}

# E2 WSL present: only the exit code of --version is read (its text is localized and undocumented).
function Testar-E2 { return ((Invoke-Wsl -Argv @('--version')).Codigo -eq 0) }
function Fazer-E2 {
    $codigo = Invoke-WslElevado -Argv @('--install', '--no-distribution')
    $script:Estado.wslInstalarCodigo = $codigo
    if ($codigo -in 0, 3010, 1641) { $script:Estado.wslInstaladoEm = Get-Agora }
    Save-Estado
    if ($codigo -eq 1223) { Stop-Instalador 'O WSL não foi instalado porque a permissão de administrador foi recusada.' }
    if ($codigo -notin 0, 3010, 1641) {
        Stop-Instalador ('A instalação do WSL falhou (código {0}). Detalhes no log: {1}' -f $codigo, $script:ArquivoLog)
    }
}

# E3 reboot. Assumptions (not documented): wsl.exe may exit 3010/1641 when a reboot is needed, and
# `wsl --version` may answer before the feature is usable. So signals only count when E2 installed WSL
# and the machine has not booted since; a pending Windows Update alone never forces a reboot.
function Test-PrecisaReiniciar {
    $e = $script:Estado
    if ($null -eq $e.wslInstaladoEm) { return $false }
    if ((Get-UltimoBoot) -gt $e.wslInstaladoEm) { return $false }
    if ($e.wslInstalarCodigo -in 3010, 1641) { return $true }
    if ((Invoke-Wsl -Argv @('--version')).Codigo -ne 0) { return $true }
    return [bool](Test-ReinicioPendenteHklm)
}
function Testar-E3 { return (-not (Test-PrecisaReiniciar)) }
function Fazer-E3 { $script:PedidoReinicio = 3 }

# E4 update: no elevation first; access denied => elevate only `wsl.exe --update`; network failure is a warning.
function Test-AcessoNegado {
    param($Resultado)
    if ($Resultado.Codigo -in 5, -2147024891) { return $true }
    return ($Resultado.Saida -match 'E_ACCESSDENIED|0x80070005|Access is denied|Acesso negado')
}
function Testar-E4 { return ($null -ne $script:Estado.wslAtualizadoEm) }
function Fazer-E4 {
    $r = Invoke-Wsl -Argv @('--update')
    $ok = ($r.Codigo -eq 0)
    if (-not $ok -and (Test-AcessoNegado $r)) { $ok = ((Invoke-WslElevado -Argv @('--update')) -eq 0) }
    if ($ok) {
        $script:Estado.wslAtualizadoEm = Get-Agora
        Save-Estado
        return
    }
    if ((Invoke-Wsl -Argv @('--version')).Codigo -ne 0) {
        Stop-Instalador ('O WSL não está funcionando e não consegui atualizá-lo. Detalhes no log: {0}' -f $script:ArquivoLog)
    }
    $script:Aviso = $true
    Write-Mensagem 'Aviso: não consegui atualizar o WSL agora (sem internet?). Sigo com a versão instalada; a próxima execução tenta de novo.'
}

# E5 rootfs download + sha256 against fixados.env.
function Get-CaminhoRootfs {
    $nome = ([uri]$script:Fixados.UBUNTU_URL).Segments[-1]
    if ($nome -notmatch '^[A-Za-z0-9._-]+$') { Stop-Instalador 'Nome de arquivo inválido em UBUNTU_URL.' 2 }
    return (Join-Path (Join-Path $script:Pasta 'baixados') $nome)
}
function Test-HashRootfs {
    param([string]$Arquivo)
    return ((Get-FileHash -LiteralPath $Arquivo -Algorithm SHA256).Hash -eq $script:Fixados.UBUNTU_SHA256)
}
function Testar-E5 {
    $arq = Get-CaminhoRootfs
    return ((Test-Path -LiteralPath $arq -PathType Leaf) -and (Test-HashRootfs $arq))
}
function Fazer-E5 {
    $arq = Get-CaminhoRootfs
    Invoke-Download -Url $script:Fixados.UBUNTU_URL -Destino $arq
    if (-not (Test-HashRootfs $arq)) {
        Remove-Item -LiteralPath $arq -Force
        Write-Log 'sha256 do Ubuntu diferente do fixados.env; arquivo apagado'
        Stop-Instalador 'O arquivo do Ubuntu baixado não confere com a assinatura esperada e foi apagado. Verifique a internet e rode de novo.'
    }
}

# E6 distro import. Only exit codes, `-l -q` names and the `-l -v` version column are parsed.
function Get-DistrosListadas {
    $r = Invoke-Wsl -Utf8 -Argv @('-l', '-q')
    # Assumption: a non-zero exit here means "no distro installed" (wsl.exe does that on an empty list).
    if ($r.Codigo -ne 0) {
        Write-Log ('wsl -l -q saiu com codigo {0}; tratado como nenhuma distro' -f $r.Codigo)
        return @()
    }
    return @($r.Saida -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}
function Get-VersaoDistro {
    param([string]$Nome)
    $r = Invoke-Wsl -Utf8 -Argv @('-l', '-v')
    foreach ($l in ($r.Saida -split "`r?`n")) {
        $t = @($l.Trim().TrimStart('*').Trim() -split '\s+')
        if ($t.Count -ge 3 -and $t[0] -eq $Nome) { return $t[-1] }
    }
    return $null
}
function Test-ErroPlataformaVm {
    param($Resultado)
    if ($Resultado.Codigo -in -2143092478, -2147220691) { return $true }
    return ($Resultado.Saida -match 'HCS_E_HYPERV_NOT_INSTALLED|0x80370102|0x8004032d|Virtual Machine Platform')
}
function Testar-E6 {
    $d = $script:Fixados.DISTRO
    if (@(Get-DistrosListadas) -notcontains $d) { return $false }
    $reg = Get-DistroRegistrada -Nome $d
    $e = $script:Estado
    $nossa = $script:EstadoExistia -and $reg -and $e.distroGuid -and $e.distroBasePath -and
        ($reg.Guid -eq $e.distroGuid) -and ($reg.BasePath -eq $e.distroBasePath)
    # A run cut off between --import and saving the GUID: adopt it only if we recorded that import here.
    if (-not $nossa -and $script:EstadoExistia -and $reg -and -not $e.distroGuid -and $e.importandoEm -and
        (Test-MesmoCaminho $e.importandoDir (Join-Path $script:Pasta 'distro')) -and (Test-MesmoCaminho $reg.BasePath $e.importandoDir)) {
        Write-Log 'distro importada numa execucao interrompida; adotada'
        $e.distroGuid = $reg.Guid
        $e.distroBasePath = $reg.BasePath
        Save-Estado
        return $true
    }
    if (-not $nossa) {
        Write-Log 'distro ja existe e nao confere com estado.json; nada foi alterado'
        Stop-Instalador "Já existe uma distro $d que não foi criada por este instalador. Nada foi alterado."
    }
    return $true
}
function Fazer-E6 {
    $d = $script:Fixados.DISTRO
    $dir = Join-Path $script:Pasta 'distro'
    # A resume at step 6 skips E5: check the rootfs hash again right before importing it.
    if (-not (Testar-E5)) {
        $arq = Get-CaminhoRootfs
        if (Test-Path -LiteralPath $arq) { Remove-Item -LiteralPath $arq -Force }
        Write-Log 'sha256 do Ubuntu diferente antes do import; arquivo apagado'
        Stop-Instalador 'O arquivo do Ubuntu não confere com a assinatura esperada e foi apagado. Rode o instalador de novo para baixá-lo outra vez.'
    }
    $script:Estado.importandoEm = Get-Agora
    $script:Estado.importandoDir = $dir
    Save-Estado
    # Importing a .wsl file through --import is not documented; measurement M8 decides (assumption).
    $r = Invoke-Wsl -Utf8 -Argv @('--import', $d, $dir, (Get-CaminhoRootfs), '--version', '2')
    if ($r.Codigo -ne 0) {
        Write-Log ('saida do wsl.exe --import: {0}' -f $r.Saida)
        if (Test-ErroPlataformaVm $r) {
            $pedido = $script:Estado.reinicioPedidoEm
            if ($null -ne $pedido -and (Get-UltimoBoot) -gt $pedido) {
                Stop-Instalador 'O Windows já reiniciou e a "Plataforma de Máquina Virtual" ainda não está ativa. Ative a virtualização na BIOS/UEFI e rode o instalador de novo.'
            }
            $script:PedidoReinicio = 6
            return
        }
        Stop-Instalador ('Não consegui criar a distro {0} (código {1}). Detalhes no log: {2}' -f $d, $r.Codigo, $script:ArquivoLog)
    }
    $reg = Get-DistroRegistrada -Nome $d
    if (-not $reg) { Stop-Instalador "A distro $d foi importada, mas não a encontrei no registro do Windows." }
    $script:Estado.distroGuid = $reg.Guid
    $script:Estado.distroBasePath = $reg.BasePath
    Save-Estado
    if ((Get-VersaoDistro -Nome $d) -ne '2') {
        if ((Invoke-Wsl -Argv @('--set-version', $d, '2')).Codigo -ne 0) {
            Stop-Instalador "Não consegui deixar a distro $d no WSL 2. Detalhes no log: $script:ArquivoLog"
        }
    }
}

function Invoke-Etapas {
    param([int]$Inicio = 1)
    $total = $script:Etapas.Count
    foreach ($e in $script:Etapas) {
        $n = $e.N
        if ($n -lt $Inicio) { continue }
        $script:EtapaAtual = $n
        $rotulo = '[{0}/{1}] {2}...' -f $n, $total, $e.Texto
        if (-not (Get-Command "Testar-E$n" -ErrorAction SilentlyContinue)) {
            Write-Mensagem "$rotulo ainda nao implementado nesta versao"
            continue
        }
        Write-Log 'inicio'
        $script:Aviso = $false
        $feito = @(& "Testar-E$n")
        if ($feito.Count -gt 0 -and $feito[-1] -eq $true) { Write-Mensagem "$rotulo ok (já estava pronto)"; continue }
        $null = & "Fazer-E$n"
        if ($script:PedidoReinicio) {
            Write-Mensagem "$rotulo é preciso reiniciar o Windows"
            return (Invoke-Reinicio -Etapa $script:PedidoReinicio)
        }
        if ([int]$script:Estado.etapa -le $n) { $script:Estado.etapa = $n + 1; Save-Estado }
        if ($script:Aviso) { Write-Mensagem "$rotulo aviso" } else { Write-Mensagem "$rotulo ok" }
    }
    Open-Projeto   # login redone while E10 was already confirmed (marker present, interop off)
    return 0
}

# Entry point used by instalar.ps1. Returns the process exit code (0 ok or reboot, 1 failure, 2 refused).
function Invoke-Instalador {
    param([switch]$Retomar, [switch]$Remover, [switch]$Login, [switch]$Atualizar, [switch]$Medir,
        [string]$Projeto, [switch]$SemReiniciar, [switch]$Forcar, [string]$Script, [string]$Fixados)
    $script:Opcoes = @{ Script = $Script; Projeto = $Projeto; SemReiniciar = [bool]$SemReiniciar
        Forcar = [bool]$Forcar; Retomar = [bool]$Retomar }
    $script:PedidoReinicio = 0
    $script:EtapaAtual = 0
    $script:ArquivoLog = $null
    if (Test-Administrador) {
        Write-Mensagem 'Não rode o instalador como administrador. Abra o PowerShell normal (sem "Executar como administrador") e rode de novo; ele pede a permissão só quando precisar.'
        return 2
    }
    if (@($Remover, $Login, $Atualizar, $Medir | Where-Object { $_ }).Count -gt 1) {
        Write-Mensagem 'Use só uma opção entre -Remover, -Login, -Atualizar e -Medir.'
        return 2
    }
    try {
        Initialize-Instalador -Fixados $Fixados
        if ($Remover) { return [int](Invoke-Remover) }
        if ($Login) { Invoke-Login; return 0 }
        if ($Atualizar) { Invoke-Atualizar; return 0 }
        if ($Medir) { return [int](Invoke-Medir) }
        $inicio = 1
        if ($Retomar) {
            Remove-RunOnce
            if ([int]$script:Estado.etapa -ge 1) { $inicio = [int]$script:Estado.etapa }
        }
        return [int](Invoke-Etapas -Inicio $inicio)
    } catch {
        $codigo = 1
        if ($_.Exception.Data.Contains('TuneUpCodigo')) {
            $codigo = [int]$_.Exception.Data['TuneUpCodigo']
            Write-Mensagem $_.Exception.Message
        } else {
            Write-Mensagem ('Erro inesperado: {0}' -f $_.Exception.Message)
        }
        try {
            if ($Retomar) {
                Write-Mensagem 'A continuação automática falhou. Depois de resolver o problema acima, rode à mão no PowerShell:'
                $manual = Get-ComandoRetomar
                Write-Mensagem $manual
            }
            Write-Log ('parou: {0}' -f $_.Exception.Message)
            if ($Retomar) { Write-Log ('comando manual: {0}' -f $manual) }
        } finally {
            # RunOnce opens a console that closes when powershell.exe exits: hold it so the text is read,
            # even when writing the log failed.
            if ($Retomar) { $null = Read-Resposta 'Aperte Enter para fechar' }
        }
        return $codigo
    }
}
