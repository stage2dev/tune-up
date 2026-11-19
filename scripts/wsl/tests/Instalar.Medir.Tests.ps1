# Pester 5 tests for -Medir (measurements M1..M9): records only, never changes the distro.
BeforeAll {
    . (Join-Path $PSScriptRoot 'Comum.ps1')
    $script:LocalOriginal = $env:LOCALAPPDATA
    function Invoke-Pronto { Invoke-InstaladorTeste | Should -Be 0; $global:TU.Argvs.Clear(); $global:TU.Msgs.Clear() }
    function Invoke-MedirTeste { Invoke-InstaladorTeste -MesmaPasta -Extra @{ Medir = $true } }
    function Get-Resumo { @($global:TU.Msgs | Where-Object { $_ -match '^M[1-9] \| ' }) }
    $script:SaidaSh = @('M3: OK - bwrap ok', 'M4: OK - echo ok', '  detalhe', 'M5: OK - cmd.exe falhou', 'M6: REGISTRO - kernel 5.15',
        'M7: REGISTRO - npm ci levou 9 s', 'M8: OK - sem uid 1000 extra') -join "`n"
}
AfterAll { $env:LOCALAPPDATA = $script:LocalOriginal; Remove-Variable -Name TU -Scope Global -ErrorAction SilentlyContinue }

Describe '-Medir' {
    BeforeEach { New-Maquina; Use-MaquinaFalsa; Invoke-Pronto; $global:TU.D.MedirSaida = $script:SaidaSh }

    It 'recopies the three files first, then runs medir.sh as tuneup with --exec' {
        Invoke-MedirTeste | Should -Be 0
        $c = @(Get-ChamadasDistro)
        @($c | Where-Object { $_ -match '/usr/bin/install' }).Count | Should -Be 3
        $c[0] | Should -Match 'install.*preparar.sh'
        $c[2] | Should -Match 'install.*fixados.env'
        @($c | Where-Object { $_ -match '^-d\|tune-up\|-u\|tuneup\|--exec\|/bin/bash\|/usr/local/lib/tune-up/medir.sh\|--tudo\|--plugin\|/mnt/c/tune-up$' }).Count | Should -Be 1
    }

    It 'issues only --exec argv, never a bare double dash, never terminate/unregister/fechar/marcar/abrir-interop' {
        $global:TU.Resposta = 's'
        Invoke-MedirTeste | Should -Be 0
        foreach ($a in $global:TU.Argvs) {
            $a[0] | Should -BeIn '-d', '-l', '--version'   # the two read-only listings and the version check
            if ($a[0] -eq '-d') { $a | Should -Contain '--exec' }
            @($a | Where-Object { $_ -eq ('-' * 2) }).Count | Should -Be 0
            @($a | Where-Object { $_ -in '--terminate', '--unregister', '--fechar', '--marcar', '--abrir-interop' }).Count | Should -Be 0
        }
        $global:TU.D.Marca | Should -BeTrue   # untouched: the finished install keeps its marker and closed interop
        $global:TU.D.Conf | Should -Be 'off'
    }

    It 'answering n skips M1 and M2 (no session, no anchor) and says they spend tokens before asking' {
        Invoke-MedirTeste | Should -Be 0
        @($global:TU.Argvs | Where-Object { $_ -contains '--bg' }).Count | Should -Be 0
        $global:TU.Ancoras.Count | Should -Be 0
        ($global:TU.Msgs -join "`n") | Should -Match 'gastam alguns tokens'
        (Get-Resumo | Where-Object { $_ -match '^M1 ' }) | Should -Match 'PULADO'
        (Get-Resumo | Where-Object { $_ -match '^M2 ' }) | Should -Match 'PULADO'
    }

    It 'answering s runs M1 without anchor and M2 with one, stops the anchor and removes both sessions' {
        $global:TU.Resposta = 's'
        $global:TU.D.AgentsSaida = '[{"id":"abc123def456","state":"working","pid":42}]'
        Invoke-MedirTeste | Should -Be 0
        ($global:TU.Ancoras -join ',') | Should -Be 'start,stop'
        @($global:TU.Argvs | Where-Object { $_ -contains '--bg' }).Count | Should -Be 2
        @($global:TU.Argvs | Where-Object { $_ -contains 'stop' -and $_ -contains 'abc123def' }).Count | Should -Be 2
        @($global:TU.Argvs | Where-Object { $_ -contains 'rm' -and $_ -contains 'abc123def' }).Count | Should -Be 2
        (Get-Resumo | Where-Object { $_ -match '^M1 ' }) | Should -Match 'M1 \| OK'
        (Get-Resumo | Where-Object { $_ -match '^M2 ' }) | Should -Match 'M2 \| OK'
    }

    It 'a session that vanished is FALHOU and the summary carries the consequence; the anchor is still stopped' {
        $global:TU.Resposta = 's'
        $global:TU.D.AgentsSaida = '[]'
        Invoke-MedirTeste | Should -Be 0
        (Get-Resumo | Where-Object { $_ -match '^M2 ' }) | Should -Match 'FALHOU.*PRECISO DE VOCÊ'
        (Get-Resumo | Where-Object { $_ -match '^M1 ' }) | Should -Match 'FALHOU.*âncora é obrigatória'
        ($global:TU.Ancoras -join ',') | Should -Be 'start,stop'
    }

    It 'a stale blocked row with no pid and no status is FALHOU, not a surviving session' {
        $global:TU.Resposta = 's'
        $global:TU.D.AgentsSaida = '[{"id":"abc123def456","state":"blocked"}]'
        Invoke-MedirTeste | Should -Be 0
        (Get-Resumo | Where-Object { $_ -match '^M1 ' }) | Should -Match 'M1 \| FALHOU'
        (Get-Resumo | Where-Object { $_ -match '^M2 ' }) | Should -Match 'M2 \| FALHOU'
    }

    It 'a done row is INCONCLUSIVO with no consequence; a blocked row with a pid is OK' {
        $global:TU.Resposta = 's'
        $global:TU.D.AgentsSaida = '[{"id":"abc123def456","state":"done","pid":42}]'
        Invoke-MedirTeste | Should -Be 0
        (Get-Resumo | Where-Object { $_ -match '^M1 ' }) | Should -Match 'M1 \| INCONCLUSIVO'
        (Get-Resumo | Where-Object { $_ -match '^M2 ' }) | Should -Not -Match 'Consequência'
        New-Maquina; Use-MaquinaFalsa; Invoke-Pronto; $global:TU.D.MedirSaida = $script:SaidaSh
        $global:TU.Resposta = 's'
        $global:TU.D.AgentsSaida = '[{"id":"abc123def456","state":"blocked","pid":42}]'
        Invoke-MedirTeste | Should -Be 0
        (Get-Resumo | Where-Object { $_ -match '^M2 ' }) | Should -Match 'M2 \| OK'
    }

    It 'the summary lists M1..M9 and the M9 round trip records the refused texts' {
        Invoke-MedirTeste | Should -Be 0
        (Get-Resumo | ForEach-Object { $_.Substring(0, 2) }) -join ',' | Should -Be 'M1,M2,M3,M4,M5,M6,M7,M8,M9'
        ($global:TU.Msgs -join "`n") | Should -Match 'recusado pelo instalador \(esperado\)'
        (Get-Resumo | Where-Object { $_ -match '^M9 ' }) | Should -Match 'M9 \| OK'
        (Get-Resumo | Where-Object { $_ -match '^M6 ' }) | Should -Match 'kernel 5.15.*Versão do WSL: 2.4.0.0'
    }

    It 'M5 FALHOU - PARE from the distro makes -Medir exit 1 and shows the consequence' {
        $global:TU.D.MedirCodigo = 9
        $global:TU.D.MedirSaida = 'M5: FALHOU - PARE: cmd.exe RODOU'
        Invoke-MedirTeste | Should -Be 1
        (Get-Resumo | Where-Object { $_ -match '^M5 ' }) | Should -Match 'PARE: o cmd.exe rodou'
    }

    It 'an unexpected medir.sh code stops with the log path; refuses when the distro is missing' {
        $global:TU.D.MedirCodigo = 3
        Invoke-MedirTeste | Should -Be 1
        $global:TU.Msgs[-1] | Should -Match 'código 3'
    }

    It 'never reads or logs the auth output' {
        $global:TU.Resposta = 's'
        Invoke-MedirTeste | Should -Be 0
        @($global:TU.Argvs | Where-Object { $_ -contains 'auth' }).Count | Should -Be 0
        ($global:TU.Msgs -join "`n") | Should -Not -Match 'SEGREDO-AUTH'
        $log = Get-ChildItem (Join-Path (Get-PastaTeste) 'logs') -Filter '*.log' | Sort-Object Name | Select-Object -Last 1
        [IO.File]::ReadAllText($log.FullName) | Should -Not -Match 'SEGREDO-AUTH'
    }
}

Describe '-Medir without the distro' {
    BeforeEach { New-Maquina; Use-MaquinaFalsa }
    It 'refuses and writes nothing' {
        Invoke-InstaladorTeste -Extra @{ Medir = $true } | Should -Be 1
        @(Get-ArgvsDeEscrita).Count | Should -Be 0
    }
}
