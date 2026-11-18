# apoio.ps1: wrappers and helpers of the tune-up WSL installer, dot-sourced by etapas.psm1 (runs in its
# module scope, so Mock -ModuleName etapas works on everything here). UTF-8 with BOM for Windows PowerShell 5.1.

function Stop-Instalador {
    param([string]$Mensagem, [int]$Codigo = 1)
    $ex = New-Object System.Exception $Mensagem
    $ex.Data['TuneUpCodigo'] = $Codigo
    throw $ex
}

function Write-Mensagem { param([string]$Texto) Write-Host $Texto }

# Own log (no Start-Transcript): timestamp, step, argv and exit codes. Callers never pass command output
# of `claude auth`, environment variables or tokens; e-mail-shaped text is masked as a safety net.
function Write-Log {
    param([string]$Texto)
    if (-not $script:ArquivoLog) { return }
    $t = $Texto -replace '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', '<e-mail>'
    $linha = '{0} [E{1}] {2}{3}' -f (Get-Date -Format 'yyyy-MM-ddTHH:mm:ss'), $script:EtapaAtual, $t, [Environment]::NewLine
    [IO.File]::AppendAllText($script:ArquivoLog, $linha, (New-Object Text.UTF8Encoding $false))
}

# Strict reader of fixados.env: never dot-sourced or evaluated, closed key list, conservative values.
function Read-Fixados {
    param([Parameter(Mandatory)][string]$Caminho)
    if (-not (Test-Path -LiteralPath $Caminho -PathType Leaf)) { Stop-Instalador "Não encontrei o arquivo fixados.env em $Caminho." 2 }
    $bytes = [IO.File]::ReadAllBytes($Caminho)
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        Stop-Instalador 'fixados.env: o arquivo não pode ter BOM.' 2
    }
    $texto = (New-Object Text.UTF8Encoding($false, $true)).GetString($bytes)
    if ($texto.Contains("`r")) { Stop-Instalador 'fixados.env: use fim de linha LF, sem CR.' 2 }
    $vals = @{}
    $n = 0
    foreach ($linha in $texto.Split("`n")) {
        $n++
        if ($linha -eq '' -or $linha.StartsWith('#')) { continue }
        $m = [regex]::Match($linha, '^([A-Z][A-Z0-9_]*)=(.*)\z')
        if (-not $m.Success) { Stop-Instalador "fixados.env, linha ${n}: não está no formato CHAVE=valor." 2 }
        $k = $m.Groups[1].Value
        $v = $m.Groups[2].Value
        if ($script:ChavesFixados -cnotcontains $k) { Stop-Instalador "fixados.env, linha ${n}: chave desconhecida $k." 2 }
        if ($vals.ContainsKey($k)) { Stop-Instalador "fixados.env, linha ${n}: chave repetida $k." 2 }
        if (-not [regex]::IsMatch($v, '^[A-Za-z0-9._:/+-]*\z')) { Stop-Instalador "fixados.env, linha ${n}: valor inválido em $k." 2 }
        $vals[$k] = $v
    }
    $faltam = @($script:ChavesFixados | Where-Object { -not $vals.ContainsKey($_) })
    if ($faltam.Count -gt 0) { Stop-Instalador ('fixados.env: faltam as chaves {0}.' -f ($faltam -join ', ')) 2 }
    return $vals
}

# Wrappers around Windows-only queries (mocked in tests).
function Get-InfoSistema {
    param([Parameter(Mandatory)][string]$Classe, [string]$Filtro)
    if ($Filtro) { return @(Get-CimInstance -ClassName $Classe -Filter $Filtro) }
    return @(Get-CimInstance -ClassName $Classe)
}

function Get-InfoWindows {
    @{ Build = [Environment]::OSVersion.Version.Build; SO64 = [Environment]::Is64BitOperatingSystem
        Processo64 = [Environment]::Is64BitProcess }
}

function Get-Agora { [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() }

function Get-UltimoBoot {
    $os = @(Get-InfoSistema -Classe Win32_OperatingSystem)[0]
    ([DateTimeOffset]$os.LastBootUpTime).ToUnixTimeSeconds()
}

function Read-Resposta { param([string]$Pergunta) Read-Host $Pergunta }

function Invoke-ReiniciarWindows { Restart-Computer }

# X:\a\b => /mnt/x/a/b, pure text (no wslpath). Refuses UNC, \\?\, relative paths and network drives.
function ConvertTo-CaminhoWsl {
    param([Parameter(Mandatory)][AllowEmptyString()][string]$Caminho)
    if ($Caminho.StartsWith('\\?\') -or $Caminho.StartsWith('//?/')) {
        Stop-Instalador "Caminhos que começam com \\?\ não são aceitos: $Caminho" 2
    }
    if ($Caminho.StartsWith('\\') -or $Caminho.StartsWith('//')) {
        Stop-Instalador "Pastas de rede (\\servidor\pasta) não são aceitas: $Caminho. Use uma pasta do próprio computador." 2
    }
    $m = [regex]::Match($Caminho, '^([A-Za-z]):[\\/]')
    if (-not $m.Success) { Stop-Instalador "Use o caminho completo da pasta, como C:\Users\voce\projeto (recebi: $Caminho)." 2 }
    $letra = $m.Groups[1].Value
    $disco = @(Get-InfoSistema -Classe Win32_LogicalDisk -Filtro ("DeviceID='{0}:'" -f $letra.ToUpperInvariant()))
    if ($disco.Count -eq 0) { Stop-Instalador "A unidade ${letra}: não existe neste computador." 2 }
    if ($disco[0].DriveType -eq 4) { Stop-Instalador "A unidade ${letra}: é uma unidade de rede. Use uma pasta do próprio computador." 2 }
    $resto = $Caminho.Substring(3).Replace('\', '/').TrimEnd('/')
    if ($resto) { return "/mnt/$($letra.ToLowerInvariant())/$resto" }
    return "/mnt/$($letra.ToLowerInvariant())"
}

function Assert-Argv {
    param([string[]]$Argv)
    foreach ($a in $Argv) {
        if ([string]::IsNullOrEmpty($a)) { Stop-Instalador 'Argumento vazio para o wsl.exe (erro interno).' }
        # A bare double dash hands the rest to the Linux shell; always use --exec with an argv instead.
        if ($a -eq ('-' * 2)) { Stop-Instalador 'Argumento proibido para o wsl.exe (erro interno).' }
    }
}

function Get-CaminhoWsl {
    if (-not $env:SystemRoot) { Stop-Instalador 'A variável SystemRoot está vazia; não sei onde está o wsl.exe.' }
    return "$env:SystemRoot\System32\wsl.exe"
}

# Runs wsl.exe by full path with an argv array; returns Codigo + Saida. -Utf8 sets WSL_UTF8=1 for the call.
# Output is never logged here; only argv and exit code.
function Invoke-Wsl {
    param([Parameter(Mandatory)][string[]]$Argv, [switch]$Utf8)
    Assert-Argv $Argv
    $exe = Get-CaminhoWsl
    if (-not (Test-Path -LiteralPath $exe)) {
        Write-Log ('wsl.exe {0} => nao encontrado' -f ($Argv -join ' '))
        return [pscustomobject]@{ Codigo = -1; Saida = '' }
    }
    $antes = $env:WSL_UTF8
    if ($Utf8) { $env:WSL_UTF8 = '1' }
    # Windows PowerShell 5.1 turns native stderr into terminating errors under 'Stop'.
    $eap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $global:LASTEXITCODE = -1
        $saida = & $exe @Argv 2>&1
        $codigo = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $eap
        $env:WSL_UTF8 = $antes
    }
    Write-Log ('wsl.exe {0} => {1}' -f ($Argv -join ' '), $codigo)
    $texto = (@($saida) | ForEach-Object { "$_" }) -join "`n"
    return [pscustomobject]@{ Codigo = [int]$codigo; Saida = ($texto -replace "`0", '') }
}

# The ONLY elevated call. Target is always the System32 wsl.exe; a cancelled UAC prompt returns 1223.
function Invoke-WslElevado {
    param([Parameter(Mandatory)][string[]]$Argv)
    Assert-Argv $Argv
    foreach ($a in $Argv) {
        if ($a -notmatch '^[A-Za-z0-9._-]+$') { Stop-Instalador "Argumento inválido para o wsl.exe como administrador: $a" }
    }
    if (-not $env:SystemRoot) { Stop-Instalador 'A variável SystemRoot está vazia; não sei onde está o wsl.exe.' }
    Write-Log ('wsl.exe (administrador) {0}' -f ($Argv -join ' '))
    try {
        $p = Start-Process -FilePath "$env:SystemRoot\System32\wsl.exe" -ArgumentList $Argv -Verb RunAs -PassThru
        $null = $p.Handle
        $p.WaitForExit()
        $codigo = $p.ExitCode
    } catch {
        $ex = $_.Exception
        while ($ex) {
            if ($ex -is [System.ComponentModel.Win32Exception] -and $ex.NativeErrorCode -eq 1223) {
                Write-Log 'administrador => cancelado'
                Write-Mensagem 'A permissão de administrador foi recusada (a janela do Windows foi cancelada). Nada foi alterado. Rode o instalador de novo e clique em "Sim".'
                return 1223
            }
            $ex = $ex.InnerException
        }
        Write-Log 'administrador => falhou ao abrir'
        Write-Mensagem ('Não consegui abrir o wsl.exe como administrador: {0}' -f $_.Exception.Message)
        return 1
    }
    if ($null -eq $codigo) { $codigo = -1 }
    Write-Log ('administrador => {0}' -f $codigo)
    return [int]$codigo
}

function Invoke-Download {
    param([Parameter(Mandatory)][string]$Url, [Parameter(Mandatory)][string]$Destino)
    if (([uri]$Url).Scheme -ne 'https') { Stop-Instalador 'Endereço de download sem https em fixados.env.' }
    $parcial = "$Destino.parcial"
    if (Test-Path -LiteralPath $parcial) { Remove-Item -LiteralPath $parcial -Force }
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $ProgressPreference = 'SilentlyContinue'
    Write-Log ('download {0}' -f (Split-Path -Leaf $Destino))
    $feito = $false
    if (Get-Command Start-BitsTransfer -ErrorAction SilentlyContinue) {
        try { Start-BitsTransfer -Source $Url -Destination $parcial; $feito = $true }
        catch { Write-Log ('BITS falhou, tentando Invoke-WebRequest: {0}' -f $_.Exception.Message) }
    }
    if (-not $feito) { Invoke-WebRequest -Uri $Url -OutFile $parcial -UseBasicParsing }
    Move-Item -LiteralPath $parcial -Destination $Destino -Force
}

# estado.json (see notes for the schema). Written atomically through a .tmp file.
function Read-Estado {
    $arq = Join-Path $script:Pasta 'estado.json'
    $script:EstadoExistia = Test-Path -LiteralPath $arq
    $h = @{ versao = 1; etapa = 1; wslInstalarCodigo = $null; wslInstaladoEm = $null; wslAtualizadoEm = $null
        reinicioPedidoEm = $null; distroGuid = $null; distroBasePath = $null }
    if ($script:EstadoExistia) {
        try { $obj = [IO.File]::ReadAllText($arq) | ConvertFrom-Json }
        catch { Stop-Instalador "O arquivo $arq está corrompido. Não apague a distro; peça ajuda ao suporte." }
        foreach ($p in $obj.PSObject.Properties) { $h[$p.Name] = $p.Value }
    }
    $script:Estado = $h
}

function Save-Estado {
    $arq = Join-Path $script:Pasta 'estado.json'
    $tmp = "$arq.tmp"
    [IO.File]::WriteAllText($tmp, ($script:Estado | ConvertTo-Json), (New-Object Text.UTF8Encoding $false))
    Move-Item -LiteralPath $tmp -Destination $arq -Force
    $script:EstadoExistia = $true
}

# Registry helpers (roots injectable). HKLM: read only.
function Get-DistroRegistrada {
    param([Parameter(Mandatory)][string]$Nome)
    $base = "$script:RaizHkcu\Software\Microsoft\Windows\CurrentVersion\Lxss"
    if (-not (Test-Path -LiteralPath $base)) { return $null }
    foreach ($k in @(Get-ChildItem -LiteralPath $base)) {
        $p = Get-ItemProperty -LiteralPath $k.PSPath
        if ($p.PSObject.Properties['DistributionName'] -and $p.DistributionName -eq $Nome) {
            $bp = $null
            if ($p.PSObject.Properties['BasePath']) { $bp = $p.BasePath }
            return [pscustomobject]@{ Guid = $k.PSChildName; BasePath = $bp }
        }
    }
    return $null
}

function Test-ReinicioPendenteHklm {
    foreach ($c in $script:ChavesReinicioHklm) {
        if (Test-Path -LiteralPath "$script:RaizHklm\$c") { return $true }
    }
    return $false
}

function Set-RunOnce {
    param([Parameter(Mandatory)][string]$Comando)
    $k = "$script:RaizHkcu\Software\Microsoft\Windows\CurrentVersion\RunOnce"
    if (-not (Test-Path -LiteralPath $k)) { $null = New-Item -Path $k -Force }
    $null = New-ItemProperty -LiteralPath $k -Name 'TuneUpWsl' -Value $Comando -PropertyType String -Force
    Write-Log 'RunOnce TuneUpWsl gravado'
}

function Remove-RunOnce {
    $k = "$script:RaizHkcu\Software\Microsoft\Windows\CurrentVersion\RunOnce"
    if ((Test-Path -LiteralPath $k) -and (Get-ItemProperty -LiteralPath $k).PSObject.Properties['TuneUpWsl']) {
        Remove-ItemProperty -LiteralPath $k -Name 'TuneUpWsl'
        Write-Log 'RunOnce TuneUpWsl removido'
    }
}

function Get-ComandoRetomar {
    $c = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}" -Retomar' -f $script:Opcoes.Script
    if ($script:Opcoes.Projeto) { $c += ' -Projeto "{0}"' -f $script:Opcoes.Projeto }
    return $c
}
