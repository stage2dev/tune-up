# medir.ps1: the -Medir mode of the tune-up WSL installer (measurements M1..M9 of the real-machine proof).
# Dot-sourced by etapas.psm1 (module scope, so Mock -ModuleName etapas works). UTF-8 with BOM for PowerShell 5.1.
# It only records: no wsl.conf edit, no wsl --terminate, no marker write. Every in-distro command is
# `wsl.exe -d <distro> [-u <user>] --exec <argv>`. Command output of `claude auth` is never read or logged.

$script:Medidas = [ordered]@{}
# Consequence text (plan table D15/F20), shown only when the result is the bad one.
$script:Consequencias = @{
    1 = 'a âncora é obrigatória (já é o padrão)'
    2 = 'a Parte C fica bloqueada. PRECISO DE VOCÊ: mande este log para o suporte'
    3 = 'pare: sem o bwrap funcionando não há estúdio'
    4 = 'a pasta de trabalho no disco Linux passa a ser obrigatória (item PC4 deixa de ser condicional)'
    5 = 'PARE: o cmd.exe rodou; isso bloqueia tudo, qualquer que seja o resto'
    8 = 'o rootfs traz um usuário com uid 1000: ajuste antes da Parte C (ou renomear o .wsl para .tar.gz e medir de novo)'
    9 = 'pare: algum byte voltou diferente'
}
$script:TextosM9 = @('C:\Users\João Silva\x', 'R$99', '$(id)', '`', "'", '%PATH%')
$script:RecusadosM9 = @('a"b', 'C:\Users\x\')

function Add-Medida {
    param([int]$N, [string]$Status, [string]$Texto)
    $l = 'M{0}: {1} - {2}' -f $N, $Status, $Texto
    Write-Mensagem $l
    Write-Log $l
    # String keys: an ordered dictionary reads an int key as a position.
    $k = "M$N"
    if (-not $script:Medidas.Contains($k)) { $script:Medidas[$k] = New-Object System.Collections.ArrayList }
    $null = $script:Medidas[$k].Add(@{ Status = $Status; Texto = $Texto })
}

function Write-Detalhe {
    param([string]$Texto)
    Write-Mensagem ('  {0}' -f $Texto)
    Write-Log ('  {0}' -f $Texto)
}

# Hidden `wsl.exe -d <distro> --exec /usr/bin/sleep infinity`: keeps the distro VM busy (M2 anchor).
function Start-Ancora {
    $a = @('-d', $script:Fixados.DISTRO, '--exec', '/usr/bin/sleep', 'infinity')
    Assert-Argv $a
    return (Start-Process -FilePath (Get-CaminhoWsl) -ArgumentList $a -WindowStyle Hidden -PassThru)
}
# Stops the anchor: a Windows process (wsl.exe), not a wsl --terminate.
function Stop-Ancora {
    param($Processo)
    if ($Processo) { try { Stop-Process -Id $Processo.Id -Force -ErrorAction Stop } catch { Write-Log 'ancora ja tinha saido' } }
}

# Launches the harmless background session the way painel/lancador.py does: claude --bg -n NAME PROMPT.
# Returns the short session id or $null.
function Start-SessaoMedida {
    param([string]$Nome)
    $prompt = 'Rode o comando sleep 170 no terminal e depois responda apenas ok.'
    $r = Invoke-Wsl -Argv @('-d', $script:Fixados.DISTRO, '-u', $script:UsuarioDistro, '--cd', '/home/tuneup', '--exec',
        '/usr/local/bin/tune-up-exec', $script:ClaudeDistro, '--bg', '-n', $Nome, $prompt)
    $m = [regex]::Match(($r.Saida -replace '\x1b\[[0-9;?]*[A-Za-z]', ''), 'backgrounded\s*\S\s*([0-9a-f]{6,16})\b')
    if ($r.Codigo -ne 0 -or -not $m.Success) { return $null }
    return $m.Groups[1].Value
}

# 'ok', 'morreu' or 'sumiu' for the session id in `claude agents --json --all` (field names as Test-LinhaViva).
function Get-EstadoSessao {
    param([string]$Id)
    $r = Invoke-NaDistro $script:UsuarioDistro @($script:ClaudeDistro, 'agents', '--json', '--all')
    $t = "$($r.Saida)".Trim()
    if ($r.Codigo -ne 0 -or -not $t.StartsWith('[')) { return 'sem-resposta' }
    try { $lista = @(ConvertFrom-Json -InputObject $t | ForEach-Object { $_ }) } catch { return 'sem-resposta' }
    foreach ($l in $lista) {
        $i = ''; $st = ''
        foreach ($p in $l.PSObject.Properties) {
            if ($p.Name -eq 'id') { $i = "$($p.Value)" }
            if ($p.Name -eq 'state') { $st = "$($p.Value)".ToLowerInvariant() }
        }
        if ($i -and ($i.StartsWith($Id) -or $Id.StartsWith($i))) {
            Write-Log ('sessao {0}: state={1}' -f $Id, $st)
            if ($st -in 'failed', 'error', 'killed', 'stopped', 'exited') { return 'morreu' }
            return 'ok'
        }
    }
    return 'sumiu'
}

function Remove-SessaoMedida {
    param([string]$Id)
    foreach ($v in 'stop', 'rm') { $null = Invoke-NaDistro $script:UsuarioDistro @($script:ClaudeDistro, $v, $Id) }
}

# M1 (no anchor) and M2 (with anchor): does the session outlive the wsl.exe that launched it, 120 s later.
function Measure-Sessao {
    param([int]$N, [switch]$ComAncora)
    $ancora = $null; $id = $null
    try {
        if ($ComAncora) { $ancora = Start-Ancora }
        $id = Start-SessaoMedida -Nome ('medir-m{0}' -f $N)
        if (-not $id) { Add-Medida $N 'FALHOU' 'não consegui lançar a sessão de teste (claude --bg); confira o login com -Login'; return }
        Write-Mensagem 'Esperando 120 segundos depois que o wsl.exe saiu...'
        Wait-Segundos 120
        $e = Get-EstadoSessao -Id $id
        if ($e -eq 'ok') { Add-Medida $N 'OK' ('a sessão continuou em claude agents 120 s depois{0}' -f $(if ($ComAncora) { ' (com âncora)' } else { ' (sem âncora)' })) }
        else { Add-Medida $N 'FALHOU' ('a sessão não sobreviveu 120 s depois ({0}){1}' -f $e, $(if ($ComAncora) { ' mesmo com âncora' } else { ' sem âncora' })) }
    } finally {
        Stop-Ancora $ancora
        if ($id) { Remove-SessaoMedida -Id $id }
    }
}

# M9 part (b): PowerShell argument round trip of installer paths and shell metacharacters, byte for byte.
function Measure-Argv {
    $bom = New-Object Text.UTF8Encoding $false
    $erros = 0
    foreach ($t in $script:TextosM9) {
        $r = Invoke-NaDistro '' @('/usr/bin/printf', '%s\n', $t)
        $volta = ($r.Saida -replace "`r?`n\z", '')
        $igual = ($r.Codigo -eq 0) -and (([BitConverter]::ToString($bom.GetBytes($volta))) -eq ([BitConverter]::ToString($bom.GetBytes($t))))
        Write-Detalhe ('M9: {0} -> {1}' -f $t, $(if ($igual) { 'bytes iguais' } else { 'DIFERENTE' }))
        if (-not $igual) { $erros++ }
    }
    foreach ($t in $script:RecusadosM9) {
        $recusado = $false
        try { Assert-Argv @($t) } catch { $recusado = $true }
        Write-Detalhe ('M9: {0} -> {1}' -f $t, $(if ($recusado) { 'recusado pelo instalador (esperado)' } else { 'NÃO recusado (inesperado)' }))
        if (-not $recusado) { $erros++ }
    }
    Write-Detalhe 'M9 parte (a) (prompt e JSON do settings pelo painel/Python) roda do painel na Parte B.'
    if ($erros -eq 0) { Add-Medida 9 'OK' 'parte (b): todos os textos voltaram iguais e os recusados foram recusados' }
    else { Add-Medida 9 'FALHOU' ('parte (b): {0} texto(s) diferente(s) ou não recusado(s)' -f $erros) }
}

function Measure-Windows {
    $v = Invoke-Wsl -Utf8 -Argv @('--version')
    foreach ($l in ($v.Saida -split "`r?`n")) { if ($l.Trim()) { Write-Detalhe ('wsl --version: {0}' -f $l.Trim()) } }
    $primeira = @($v.Saida -split "`r?`n" | Where-Object { $_.Trim() })
    Add-Medida 6 'REGISTRO' ('wsl.exe --version saiu com {0}: {1}' -f $v.Codigo, $(if ($primeira) { $primeira[0].Trim() } else { '(sem saída)' }))
    $e = $script:Estado
    $direto = if ($e.distroGuid) { 'sim (o instalador só importa o .wsl direto e a distro está registrada)' } else { 'não confirmado (sem distroGuid no estado)' }
    Add-Medida 8 'REGISTRO' ('rootfs .wsl importado direto: {0}; wsl --install saiu com {1}' -f $direto, $e.wslInstalarCodigo)
}

function Write-ResumoMedidas {
    Write-Mensagem ''
    Write-Mensagem 'Resumo das medições'
    foreach ($n in 1..9) {
        $itens = @(if ($script:Medidas.Contains("M$n")) { $script:Medidas["M$n"] })
        if ($itens.Count -eq 0) { $itens = @(@{ Status = 'PULADO'; Texto = 'não medido' }) }
        $ruim = @($itens | Where-Object { $_.Status -eq 'FALHOU' }).Count -gt 0
        $linha = 'M{0} | {1} | {2}' -f $n, (@($itens | ForEach-Object { $_.Status }) -join '+'), ((@($itens | ForEach-Object { $_.Texto }) -join ' / '))
        if ($ruim -and $script:Consequencias.ContainsKey($n)) { $linha += ' | Consequência: ' + $script:Consequencias[$n] }
        Write-Mensagem $linha
        Write-Log $linha
    }
}

function Invoke-Medir {
    $script:Medidas = [ordered]@{}
    Assert-DistroNossa
    Copy-ArquivosDistro
    $r = Invoke-NaDistro $script:UsuarioDistro @('/bin/bash', "$script:LibDistro/medir.sh", '--tudo', '--plugin', (Get-RaizRepoWsl))
    $pare = ($r.Codigo -eq 9)
    if ($r.Codigo -notin 0, 9) { Stop-Instalador ('A medição dentro da distro parou (código {0}). Detalhes no log: {1}' -f $r.Codigo, $script:ArquivoLog) }
    foreach ($l in ($r.Saida -split "`r?`n")) {
        if ($l -match '^M([1-9]): (\S+) - (.*)$') { Add-Medida ([int]$Matches[1]) $Matches[2] $Matches[3] }
        elseif ($l.Trim()) { Write-Detalhe $l.Trim() }
    }
    Measure-Windows
    Measure-Argv
    Write-Mensagem 'As medições M1 e M2 usam a sua conta do Claude e gastam alguns tokens.'
    $resp = "$(Read-Resposta 'Rodar M1 e M2 agora? (s/N)')".Trim().ToLowerInvariant()
    if ($resp -in 's', 'sim') {
        Measure-Sessao -N 1
        Measure-Sessao -N 2 -ComAncora
    } else {
        Write-Log 'M1 e M2 puladas a pedido'
    }
    Write-ResumoMedidas
    return $(if ($pare) { 1 } else { 0 })
}
