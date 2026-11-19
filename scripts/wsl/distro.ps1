# distro.ps1: steps E7-E10 and the -Login, -Atualizar and -Remover modes of the tune-up WSL installer.
# Dot-sourced by etapas.psm1 (module scope, so Mock -ModuleName etapas works). UTF-8 with BOM for PowerShell 5.1.
# Every in-distro command is `wsl.exe -d <distro> [-u <user>] --exec <argv>`: never a Linux command string.

$script:UsuarioDistro = 'tuneup'
$script:ClaudeDistro = '/home/tuneup/.local/bin/claude'
$script:MarcaDistro = '/etc/tune-up/pronto.json'
$script:LibDistro = '/usr/local/lib/tune-up'
# cmd.exe re-reads its line and wt.exe splits subcommands on ';' (same set as painel/abrir_win.py).
$script:MetacharWin = '[&|<>^%!"();]'

function Invoke-NaDistro {
    param([AllowEmptyString()][string]$Usuario, [Parameter(Mandatory)][string[]]$Comando)
    $a = @('-d', $script:Fixados.DISTRO)
    if ($Usuario) { $a += @('-u', $Usuario) }
    return (Invoke-Wsl -Argv ($a + @('--exec') + $Comando))
}

function Invoke-Preparar {
    param([Parameter(Mandatory)][string]$Usuario, [Parameter(Mandatory)][string[]]$Modo)
    return (Invoke-NaDistro $Usuario (@('/bin/bash', "$script:LibDistro/preparar.sh") + $Modo))
}

function Stop-Preparar {
    param([string]$Modo, [int]$Codigo)
    $motivo = switch ($Codigo) {
        3 { 'o comando rodou com o usuário errado (erro interno do instalador)' }
        4 { 'o arquivo fixados.env copiado para a distro está inválido' }
        5 { 'um download falhou ou não conferiu com a assinatura esperada (sha256); verifique a internet e rode de novo' }
        6 { 'o Ubuntu baixado já trouxe um usuário com o número 1000, e o tune-up precisa desse número. Esta distro não serve; rode o instalador com -Remover e peça ajuda ao suporte' }
        7 { 'a ponte com o Windows (interop) ainda está ligada' }
        8 { 'o plugin instalado na distro não passou na conferência' }
        default { "falhou (código $Codigo)" }
    }
    Stop-Instalador ('A preparação da distro ({0}) parou: {1}. Detalhes no log: {2}' -f $Modo, $motivo, $script:ArquivoLog)
}

function Get-RaizRepoWsl { return (ConvertTo-CaminhoWsl -Caminho $script:RaizRepo) }

# Plugin version on the Windows side: <repo root>\.claude-plugin\plugin.json.
function Get-VersaoPlugin {
    $arq = Join-Path (Join-Path $script:RaizRepo '.claude-plugin') 'plugin.json'
    try { $v = ([IO.File]::ReadAllText($arq) | ConvertFrom-Json).version }
    catch { Stop-Instalador "Não consegui ler a versão do plugin em $arq." }
    if ("$v" -notmatch '^\d+\.\d+\.\d+\z') { Stop-Instalador "A versão do plugin em $arq não é do tipo 1.2.3." }
    return "$v"
}

function Get-ComandoInstalar {
    param([switch]$Login)
    $c = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $script:Opcoes.Script
    if ($Login) { $c += ' -Login' }
    return $c
}

function Wait-Segundos { param([int]$Segundos) Start-Sleep -Seconds $Segundos }

# Opens a new Windows Terminal tab (or a cmd window when wt.exe is missing) running the given wsl.exe argv.
# Returns $false, opening nothing, when an argument holds a cmd/wt metacharacter. Elements with spaces are
# quoted here because Start-Process joins -ArgumentList with spaces (Assert-Argv already refused '"' and a
# trailing backslash).
function ConvertTo-ArgvCitado {
    param([string[]]$Argv)
    return @($Argv | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } })
}
function Start-Terminal {
    param([Parameter(Mandatory)][string[]]$Argv)
    Assert-Argv $Argv
    foreach ($a in $Argv) { if ($a -match $script:MetacharWin) { return $false } }
    $lista = ConvertTo-ArgvCitado $Argv
    $wt = @(Get-Command 'wt.exe' -CommandType Application -ErrorAction SilentlyContinue) | Select-Object -First 1
    if ($wt) {
        Start-Process -FilePath $wt.Source -ArgumentList (@('-w', '0', 'nt') + $lista)
    } else {
        Start-Process -FilePath "$env:SystemRoot\System32\cmd.exe" -ArgumentList (@('/c', 'start', '""') + $lista)
    }
    return $true
}

# Copies preparar.sh, medir.sh and fixados.env into the distro as root with /usr/bin/install (reads /mnt,
# never executes from it). medir.sh is optional until the item that creates it lands.
function Copy-ArquivosDistro {
    $origem = Join-Path (Join-Path $script:RaizRepo 'scripts') 'wsl'
    $wsl = (Get-RaizRepoWsl) + '/scripts/wsl'
    foreach ($a in @(@('preparar.sh', '0755'), @('medir.sh', '0755'), @('fixados.env', '0644'))) {
        if (-not (Test-Path -LiteralPath (Join-Path $origem $a[0]) -PathType Leaf)) {
            if ($a[0] -eq 'medir.sh') { Write-Log 'medir.sh nao existe nesta copia do repositorio; nao copiado'; continue }
            Stop-Instalador ('Não encontrei {0} em {1}.' -f $a[0], $origem)
        }
        $r = Invoke-NaDistro 'root' @('/usr/bin/install', '-D', '-o', 'root', '-g', 'root', '-m', $a[1],
            "$wsl/$($a[0])", "$script:LibDistro/$($a[0])")
        if ($r.Codigo -ne 0) { Stop-Instalador ('Não consegui copiar {0} para a distro (código {1}).' -f $a[0], $r.Codigo) }
    }
}

function Remove-Marca {
    $r = Invoke-NaDistro 'root' @('/bin/rm', '-f', $script:MarcaDistro)
    if ($r.Codigo -ne 0) { Stop-Instalador ('Não consegui apagar a marca de pronto da distro (código {0}).' -f $r.Codigo) }
}

# One `claude agents --json --all` row counts as live when painel/agentes.py (_estado_basico, no idle
# time known) maps it to rodando or precisa_de_voce: the same field names (state, status) and values.
function Test-LinhaViva {
    param($Linha)
    $st = ''; $ss = ''
    foreach ($p in $Linha.PSObject.Properties) {
        if ($p.Name -eq 'state') { $st = "$($p.Value)".ToLowerInvariant() }
        if ($p.Name -eq 'status') { $ss = "$($p.Value)".ToLowerInvariant() }
    }
    if ($st -eq 'blocked' -or $ss -eq 'waiting' -or $ss -eq 'busy') { return $true }
    if ($st -in 'working', 'running', 'busy', 'active') { return $true }
    if ($st -in 'done', 'completed', 'finished', 'stopped', 'killed', 'failed', 'error', 'exited') { return $false }
    return ($ss -ne 'idle')
}

# Live-session lock, run before every --terminate and --unregister. Field names follow painel/agentes.py
# (measured on CLI 2.1.322, not confirmed for the pinned version). Assumption kept from A3b: exit 0 with
# empty output means no session. Output that is not a JSON array refuses (fail closed); so does any other
# failure. -Forcar overrides. The command output is never logged or shown.
function Test-SessaoViva {
    $u = $script:UsuarioDistro
    $c = Invoke-NaDistro $u @('/usr/bin/test', '-x', $script:ClaudeDistro)
    $cod = $c.Codigo
    if ($cod -eq 1) {
        # exit 1 means "no binary" only when the user's home is really there (else -u tuneup itself failed)
        if ((Invoke-NaDistro $u @('/usr/bin/test', '-d', '/home/tuneup')).Codigo -eq 0) { Write-Log 'trava: claude nao instalado, sem sessao'; return }
        $cod = -1
    }
    $motivo = $null
    if ($cod -ne 0) {
        $motivo = 'Não consegui conferir se o Claude está aberto na distro'
    } else {
        $r = Invoke-NaDistro $u @($script:ClaudeDistro, 'agents', '--json', '--all')
        $t = "$($r.Saida)".Trim()
        if ($r.Codigo -ne 0) {
            $motivo = 'Não consegui conferir as sessões abertas do Claude na distro (o login pode ter expirado)'
        } elseif ($t) {
            $n = -1
            if ($t.StartsWith('[')) {
                try {
                    $n = @(ConvertFrom-Json -InputObject $t | ForEach-Object { $_ } |
                        Where-Object { $_ -is [Management.Automation.PSCustomObject] -and (Test-LinhaViva $_) }).Count
                } catch { $n = -1 }
            }
            if ($n -lt 0) { $motivo = 'Não entendi a resposta do Claude sobre as sessões abertas' }
            elseif ($n -gt 0) { $motivo = 'Há {0} sessão(ões) do Claude aberta(s) na distro' -f $n }
        }
    }
    if (-not $motivo) { Write-Log 'trava: nenhuma sessao aberta'; return }
    if ($script:Opcoes.Forcar) {
        Write-Log 'trava: recusaria, ignorada por -Forcar'
        Write-Mensagem "Aviso: $motivo. Sigo assim mesmo por causa de -Forcar; o que estiver aberto será fechado."
        return
    }
    Write-Log 'trava: recusou'
    Stop-Instalador "$motivo. Nada foi fechado. Feche as janelas do Claude na distro tune-up e rode de novo, ou rode com -Forcar para fechar assim mesmo."
}

function Stop-Distro {
    Test-SessaoViva
    $r = Invoke-Wsl -Argv @('--terminate', $script:Fixados.DISTRO)
    if ($r.Codigo -ne 0) { Stop-Instalador ('Não consegui reiniciar a distro (código {0}).' -f $r.Codigo) }
}

function Set-Marca {
    param([switch]$Atualizar)
    $r = Invoke-Preparar 'root' @('--marcar', '--plugin-versao', (Get-VersaoPlugin))
    if ($r.Codigo -eq 7) {
        if ($Atualizar) {
            Stop-Instalador ('A ponte com o Windows ainda está ligada, então a distro não foi marcada como pronta. Rode {0} ou o instalador completo: {1}' -f (Get-ComandoInstalar -Login), (Get-ComandoInstalar))
        }
        Stop-Instalador ('A ponte com o Windows continua ligada depois de reiniciar a distro, então ela não foi marcada como pronta. Rode de novo: {0}' -f (Get-ComandoInstalar))
    }
    if ($r.Codigo -ne 0) { Stop-Preparar '--marcar' $r.Codigo }
}

# E7 root part: helpers, user, Node, FFmpeg and the install-phase wsl.conf (default user tuneup).
function Testar-E7 {
    if ((Invoke-NaDistro 'root' @('/usr/bin/test', '-x', '/usr/local/bin/tune-up-exec')).Codigo -ne 0) { return $false }
    $n = Invoke-NaDistro 'root' @('/usr/local/bin/node', '--version')
    if ($n.Codigo -ne 0 -or "$($n.Saida)".Trim() -ne ('v' + $script:Fixados.NODE_VERSAO)) { return $false }
    $u = Invoke-NaDistro '' @('/usr/bin/id', '-un')
    return ($u.Codigo -eq 0 -and "$($u.Saida)".Trim() -eq $script:UsuarioDistro)
}
function Fazer-E7 {
    Remove-Marca
    Copy-ArquivosDistro
    $r = Invoke-Preparar 'root' @('--raiz')
    if ($r.Codigo -ne 0) { Stop-Preparar '--raiz' $r.Codigo }
    Stop-Distro   # the new wsl.conf (default user, interop) applies on the next start
}

# E8 user part: Claude Code, plugin, Chrome, HyperFrames.
function Testar-E8 {
    $v = Invoke-Preparar $script:UsuarioDistro @('--versao-plugin')
    if ($v.Codigo -ne 0 -or "$($v.Saida)".Trim() -ne (Get-VersaoPlugin)) { return $false }
    if ((Invoke-NaDistro $script:UsuarioDistro @('/usr/bin/test', '-x', $script:ClaudeDistro)).Codigo -ne 0) { return $false }
    # a half-failed --usuario (Chrome or HyperFrames) keeps the new plugin version: verify the whole install
    return ((Invoke-Preparar $script:UsuarioDistro @('--verificar', '--plugin', (Get-RaizRepoWsl))).Codigo -eq 0)
}
function Fazer-E8 {
    Remove-Marca   # a redone E8 must redo E10 and re-mark with the new plugin version
    $r = Invoke-Preparar $script:UsuarioDistro @('--usuario', '--plugin', (Get-RaizRepoWsl))
    if ($r.Codigo -ne 0) { Stop-Preparar '--usuario' $r.Codigo }
}

# E9 login. `claude auth status` output is never logged or shown (Invoke-Wsl logs argv and exit code only).
function Test-Login {
    return ((Invoke-NaDistro $script:UsuarioDistro @($script:ClaudeDistro, 'auth', 'status')).Codigo -eq 0)
}
function Testar-E9 { return (Test-Login) }
function Fazer-E9 {
    param([switch]$Login)
    $wsl = Get-CaminhoWsl
    $base = @($wsl, '-d', $script:Fixados.DISTRO, '-u', $script:UsuarioDistro)
    $argv = $base + @('--cd', '~', '--exec', '/usr/bin/env', 'BROWSER=/usr/local/bin/tune-up-abrir', $script:ClaudeDistro, 'auth', 'login')
    if (-not (Start-Terminal -Argv $argv)) {
        Stop-Instalador ('Não consegui abrir uma janela nova. Rode este comando no PowerShell e depois rode o instalador de novo: {0}' -f ((ConvertTo-ArgvCitado $argv) -join ' '))
    }
    Write-Mensagem 'Abri uma janela nova para você entrar na sua conta do Claude. Siga o que aparece nela; eu espero aqui por até 15 minutos.'
    $limite = (Get-Agora) + 900
    while ($true) {
        Wait-Segundos 5
        if (Test-Login) { break }
        if ((Get-Agora) -ge $limite) {
            Stop-Instalador ('O login não terminou em 15 minutos. Quando puder, rode de novo: {0}' -f (Get-ComandoInstalar -Login:$Login))
        }
    }
    Write-Log 'login confirmado'
    # The project window opens only after the marker is written (interop off): see Open-Projeto.
    $script:ProjetoPendente = [bool]$script:Opcoes.Projeto
}

# Opens claude in the -Projeto folder so the person accepts the folder trust. Called only once the
# marker is written or already confirmed, i.e. after --fechar and --terminate: the project's hooks
# must never run in a session where interop is still on.
function Open-Projeto {
    if (-not $script:ProjetoPendente) { return }
    $script:ProjetoPendente = $false
    $proj = @((Get-CaminhoWsl), '-d', $script:Fixados.DISTRO, '-u', $script:UsuarioDistro,
        '--cd', (ConvertTo-CaminhoWsl -Caminho $script:Opcoes.Projeto), '--exec', $script:ClaudeDistro)
    if (Start-Terminal -Argv $proj) {
        Write-Mensagem 'Abri o Claude na pasta do projeto: aceite a confiança na pasta e feche.'
    } else {
        Write-Mensagem ('Não consegui abrir o Claude na pasta do projeto. Depois, rode: {0}' -f ((ConvertTo-ArgvCitado $proj) -join ' '))
    }
}

# E10 close: verify, final wsl.conf, lock, terminate, then the marker (only written with interop off).
function Testar-E10 {
    if ((Invoke-NaDistro 'root' @('/usr/bin/test', '-f', $script:MarcaDistro)).Codigo -ne 0) { return $false }
    return ((Invoke-NaDistro '' @('/usr/bin/printenv', 'WSL_INTEROP')).Codigo -eq 1)
}
function Fazer-E10 {
    $r = Invoke-Preparar $script:UsuarioDistro @('--verificar', '--plugin', (Get-RaizRepoWsl))
    Write-Mensagem $r.Saida
    Write-Log ("relatorio do --verificar (codigo {0}):`n{1}" -f $r.Codigo, $r.Saida)
    if ($r.Codigo -ne 0) { Stop-Instalador 'A conferência final encontrou problemas (veja acima). A distro não foi fechada nem marcada como pronta. Corrija e rode o instalador de novo.' }
    $f = Invoke-Preparar 'root' @('--fechar')
    if ($f.Codigo -ne 0) { Stop-Preparar '--fechar' $f.Codigo }
    Stop-Distro
    Set-Marca
    Open-Projeto
}

function Assert-DistroNossa {
    if (-not (Testar-E6)) { Stop-Instalador ('A distro {0} não está instalada. Rode o instalador sem opções primeiro.' -f $script:Fixados.DISTRO) }
}

function Invoke-Login {
    Assert-DistroNossa
    $script:EtapaAtual = 9
    Test-SessaoViva   # refuse before touching the marker or wsl.conf
    Remove-Marca
    $r = Invoke-Preparar 'root' @('--abrir-interop')
    if ($r.Codigo -ne 0) { Stop-Preparar '--abrir-interop' $r.Codigo }
    Stop-Distro
    Fazer-E9 -Login
    $script:EtapaAtual = 10
    Fazer-E10
    Write-Mensagem 'Login feito e distro fechada de novo. Pronto.'
}

function Invoke-Atualizar {
    Assert-DistroNossa
    $script:EtapaAtual = 8
    Copy-ArquivosDistro
    Fazer-E8
    Set-Marca -Atualizar
    Write-Mensagem 'Plugin atualizado na distro. Pronto.'
}

function Test-MesmoCaminho {
    param([string]$A, [string]$B)
    if (-not $A -or -not $B) { return $false }
    $n = { param($x) ($x -replace '^\\\\\?\\', '').TrimEnd('\', '/') }
    return ((& $n $A) -eq (& $n $B))
}

# Post-order list of everything under $Dir; refuses (before anything is deleted) on any link or junction,
# so a recursive delete can never follow one out of our folder.
function Get-ItensArvore {
    param([IO.DirectoryInfo]$Dir)
    foreach ($i in $Dir.GetFileSystemInfos()) {
        if ($i.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            Stop-Instalador ('Encontrei um atalho (link ou junção) em {0}. Não apago nada; apague a pasta à mão.' -f $i.FullName)
        }
        if ($i -is [IO.DirectoryInfo]) { Get-ItensArvore $i }
        $i
    }
}

# Checks that the folder is exactly %LOCALAPPDATA%\tune-up\wsl and holds no link anywhere; returns the
# folder (or $null when it does not exist). Run before --unregister and again right before deleting.
function Get-PastaParaApagar {
    $esperada = Join-Path (Join-Path $env:LOCALAPPDATA 'tune-up') 'wsl'
    $p = $script:Pasta
    if (-not (Test-MesmoCaminho $p $esperada)) { Stop-Instalador "Recusei apagar ${p}: não é a pasta do instalador." }
    if (-not (Test-Path -LiteralPath $p)) { return $null }
    $raiz = New-Object IO.DirectoryInfo $p
    foreach ($x in @($raiz, $raiz.Parent)) {
        if ($x.Attributes -band [IO.FileAttributes]::ReparsePoint) { Stop-Instalador "Recusei apagar ${p}: $($x.FullName) é um atalho (link ou junção)." }
    }
    $null = @(Get-ItensArvore $raiz)
    return $raiz
}

function Remove-PastaSegura {
    $raiz = Get-PastaParaApagar
    if (-not $raiz) { return }
    $itens = @(Get-ItensArvore $raiz)
    $script:ArquivoLog = $null   # the log lives inside the folder being deleted
    foreach ($i in $itens) {
        if ($i -is [IO.FileInfo]) { $i.Attributes = [IO.FileAttributes]::Normal }
        $i.Delete()
    }
    $raiz.Delete()
}

function Invoke-Remover {
    $d = $script:Fixados.DISTRO
    $reg = Get-DistroRegistrada -Nome $d
    $listada = @(Get-DistrosListadas) -contains $d
    $dirDistro = Join-Path $script:Pasta 'distro'
    Write-Mensagem 'Isto apaga, sem volta:'
    if ($listada -or $reg) {
        $bp = if ($reg) { $reg.BasePath } else { '(não encontrada no registro)' }
        Write-Mensagem ("  - a distro {0} e tudo dentro dela (pasta {1})" -f $d, $bp)
    }
    Write-Mensagem ("  - a pasta {0} (estado, downloads e logs)" -f $script:Pasta)
    $r = Read-Resposta "Para confirmar, digite $d"
    if ("$r" -cne $d) { Write-Mensagem 'Nada foi apagado.'; Write-Log 'remover: nao confirmado'; return 1 }
    if ($listada -or $reg) {
        if (-not $reg) { Stop-Instalador "A distro $d aparece no WSL mas não no registro do Windows. Nada foi apagado." }
        $e = $script:Estado
        if ($script:EstadoExistia -and $e.distroGuid) {
            if ($reg.Guid -ne $e.distroGuid -or -not (Test-MesmoCaminho $reg.BasePath $e.distroBasePath)) {
                Stop-Instalador "A distro $d não confere com a que este instalador criou. Nada foi apagado."
            }
        } else {
            $dentro = (Test-MesmoCaminho $reg.BasePath $dirDistro) -or
                (($reg.BasePath -replace '^\\\\\?\\', '').StartsWith($dirDistro.TrimEnd('\', '/') + '\', [StringComparison]::OrdinalIgnoreCase))
            if (-not $script:Opcoes.Forcar -or -not $dentro) {
                Stop-Instalador "Não encontrei o registro deste instalador sobre a distro $d. Só apago com -Forcar e se ela estiver em $dirDistro. Nada foi apagado."
            }
            Write-Log 'remover: sem estado.json, aceito por -Forcar e BasePath dentro da pasta'
        }
        $null = Get-PastaParaApagar
        Test-SessaoViva
        $u = Invoke-Wsl -Argv @('--unregister', $d)
        if ($u.Codigo -ne 0) { Stop-Instalador ('Não consegui apagar a distro {0} (código {1}). A pasta {2} foi mantida.' -f $d, $u.Codigo, $script:Pasta) }
    }
    Remove-RunOnce
    Remove-PastaSegura
    Write-Mensagem "Pronto: a distro $d e a pasta do instalador foram apagadas."
    return 0
}
