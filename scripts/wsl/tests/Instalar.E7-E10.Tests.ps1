# Pester 5 tests for steps E7 to E10 (distro.ps1) against the fake distro of Comum.ps1.
BeforeAll {
    . (Join-Path $PSScriptRoot 'Comum.ps1')
    $script:LocalOriginal = $env:LOCALAPPDATA
    $script:R = '-d|tune-up|-u|root|--exec|'
    $script:T = '-d|tune-up|-u|tuneup|--exec|'
    $script:P = '/bin/bash|/usr/local/lib/tune-up/preparar.sh|'
    function Get-Indice([string]$Parte) {
        $c = Get-ChamadasDistro
        for ($i = 0; $i -lt $c.Count; $i++) { if ($c[$i].Contains($Parte)) { return $i } }
        return -1
    }
    function Get-UltimoIndice([string]$Parte) {
        $c = Get-ChamadasDistro
        for ($i = $c.Count - 1; $i -ge 0; $i--) { if ($c[$i].Contains($Parte)) { return $i } }
        return -1
    }
}
AfterAll { $env:LOCALAPPDATA = $script:LocalOriginal; Remove-Variable -Name TU -Scope Global -ErrorAction SilentlyContinue }

Describe 'E7..E10 full run' {
    BeforeEach { New-Maquina; Use-MaquinaFalsa }

    It 'issues the exact in-distro argv in order' {
        Invoke-InstaladorTeste | Should -Be 0
        $copia = @("${R}/usr/bin/install|-D|-o|root|-g|root|-m|0755|/mnt/c/tune-up/scripts/wsl/preparar.sh|/usr/local/lib/tune-up/preparar.sh")
        if (Test-Path (Join-Path $RaizWsl 'medir.sh')) {
            $copia += "${R}/usr/bin/install|-D|-o|root|-g|root|-m|0755|/mnt/c/tune-up/scripts/wsl/medir.sh|/usr/local/lib/tune-up/medir.sh"
        }
        $copia += "${R}/usr/bin/install|-D|-o|root|-g|root|-m|0644|/mnt/c/tune-up/scripts/wsl/fixados.env|/usr/local/lib/tune-up/fixados.env"
        $esperado = @("${R}/usr/bin/test|-x|/usr/local/bin/tune-up-exec", "${R}/bin/rm|-f|/etc/tune-up/pronto.json") + $copia + @(
            "${R}${P}--raiz",
            "${T}/usr/bin/test|-x|/home/tuneup/.local/bin/claude",
            "${T}/usr/bin/test|-d|/home/tuneup",
            '--terminate|tune-up',
            "${T}${P}--versao-plugin",
            "${R}/bin/rm|-f|/etc/tune-up/pronto.json",
            "${T}${P}--usuario|--plugin|/mnt/c/tune-up",
            "${T}/home/tuneup/.local/bin/claude|auth|status",
            "${R}/usr/bin/test|-f|/etc/tune-up/pronto.json",
            "${T}${P}--verificar|--plugin|/mnt/c/tune-up",
            "${R}${P}--fechar",
            "${T}/usr/bin/test|-x|/home/tuneup/.local/bin/claude",
            "${T}/home/tuneup/.local/bin/claude|agents|--json|--all",
            '--terminate|tune-up',
            "${R}${P}--marcar|--plugin-versao|$VersaoPluginReal")
        (Get-ChamadasDistro) -join "`n" | Should -BeExactly ($esperado -join "`n")
        $global:TU.D.Marca | Should -BeTrue
        $global:TU.D.Interop | Should -BeFalse
    }

    It 'every in-distro argv has --exec, no bare double dash, and never executes from /mnt' {
        Invoke-InstaladorTeste | Should -Be 0
        $dentro = @($global:TU.Argvs | Where-Object { $_[0] -eq '-d' })
        $dentro.Count | Should -BeGreaterThan 10
        foreach ($a in $dentro) {
            $a | Should -Contain '--exec'
            $a | Should -Not -Contain '--'
            $i = [array]::IndexOf($a, '--exec')
            $a[$i + 1] | Should -Not -Match '^/mnt/'
            if ($a[$i + 1] -eq '/bin/bash') { $a[$i + 2] | Should -Not -Match '^/mnt/' }
            foreach ($x in $a) { if ($x -like '/mnt/*') { $a[$i + 1] | Should -BeIn @('/usr/bin/install', '/bin/bash') } }
        }
        foreach ($a in @($global:TU.Argvs | Where-Object { $_ -contains '/usr/bin/install' })) {
            ($a[0..4] -join ' ') | Should -Be '-d tune-up -u root --exec'
            $a[-2] | Should -Match '^/mnt/c/'
            $a[-1] | Should -Match '^/usr/local/lib/tune-up/'
        }
    }

    It 'E7 deletes the marker before --raiz and terminates only after the lock' {
        Invoke-InstaladorTeste | Should -Be 0
        (Get-Indice '/bin/rm|-f|/etc/tune-up/pronto.json') | Should -BeLessThan (Get-Indice '--raiz')
        $term = Get-Indice '--terminate'
        $term | Should -BeGreaterThan (Get-Indice '--raiz')
        (Get-Indice '/usr/bin/test|-x|/home/tuneup/.local/bin/claude') | Should -BeLessThan $term
    }

    It 'E7 with a live session already in the distro stops before --terminate' {
        $global:TU.D.TesteClaude = 0; $global:TU.D.AgentsSaida = '[{"id":"a"}]'
        Invoke-InstaladorTeste | Should -Be 1
        (Get-Indice '--terminate') | Should -Be -1
        (Get-Indice '--versao-plugin') | Should -Be -1
        ($global:TU.Msgs -join "`n") | Should -Match '1 sessão'
    }

    It 'E7 maps preparar.sh exit <Codigo>' -ForEach @(
        @{ Codigo = 6; Texto = 'número 1000' }
        @{ Codigo = 5; Texto = 'sha256' }
    ) {
        $global:TU.D.Codigos['--raiz'] = $Codigo
        Invoke-InstaladorTeste | Should -Be 1
        ($global:TU.Msgs -join "`n") | Should -Match $Texto
        (Get-Indice '--terminate') | Should -Be -1
    }

    It 'E8 is redone when the plugin versions differ, deleting the marker first so E10 re-marks' {
        Invoke-InstaladorTeste | Should -Be 0
        $global:TU.D.Plugin = '0.0.1'; $global:TU.Argvs.Clear()
        Invoke-InstaladorTeste -MesmaPasta | Should -Be 0
        @(Get-ChamadasDistro | Where-Object { $_ -like '*--usuario*' }).Count | Should -Be 1
        $global:TU.D.Plugin | Should -Be $VersaoPluginReal
        (Get-Indice '--raiz') | Should -Be -1
        (Get-Indice '/bin/rm|-f|/etc/tune-up/pronto.json') | Should -BeLessThan (Get-Indice '--usuario')
        (Get-Indice '/bin/rm|-f|/etc/tune-up/pronto.json') | Should -BeGreaterThan -1
        (Get-Indice "--marcar|--plugin-versao|$VersaoPluginReal") | Should -BeGreaterThan (Get-Indice '--usuario')
        $global:TU.D.Marca | Should -BeTrue
    }

    It 'E8 is redone when the plugin version matches but --verificar fails (half-failed --usuario)' {
        Invoke-InstaladorTeste | Should -Be 0
        $global:TU.D.Parcial = $true; $global:TU.Argvs.Clear()
        Invoke-InstaladorTeste -MesmaPasta | Should -Be 0
        (Get-Indice '--verificar') | Should -BeLessThan (Get-Indice '--usuario')
        @(Get-ChamadasDistro | Where-Object { $_ -like '*--usuario*' }).Count | Should -Be 1
        (Get-Indice '--marcar') | Should -BeGreaterThan (Get-Indice '--usuario')
    }

    It 'E10: --verificar failing stops before --fechar, shows and logs the report' {
        $global:TU.D.Codigos['--verificar'] = 1
        Invoke-InstaladorTeste | Should -Be 1
        (Get-Indice '--fechar') | Should -Be -1
        (Get-Indice '--marcar') | Should -Be -1
        $global:TU.Msgs | Should -Contain 'RELATORIO-VERIFICAR'
        (Get-ChildItem (Join-Path (Get-PastaTeste) 'logs') | Get-Content -Raw) | Should -Match 'RELATORIO-VERIFICAR'
    }

    It 'E10 runs --fechar, lock, --terminate, --marcar in that order' {
        Invoke-InstaladorTeste | Should -Be 0
        $f = Get-Indice '--fechar'
        $lock = Get-UltimoIndice 'agents|--json'
        $t = Get-UltimoIndice '--terminate'
        $m = Get-Indice '--marcar'
        $f | Should -BeLessThan $lock
        $lock | Should -BeLessThan $t
        $t | Should -BeLessThan $m
    }

    It 'E10 with the lock refusing never calls --marcar; -Forcar passes' {
        $global:TU.D.AgentsSaida = '[{"id":"a"},{"id":"b"}]'
        Invoke-InstaladorTeste | Should -Be 1
        (Get-Indice '--fechar') | Should -BeGreaterThan -1
        (Get-Indice '--marcar') | Should -Be -1
        (Get-UltimoIndice '--terminate') | Should -BeLessThan (Get-Indice '--fechar')
        ($global:TU.Msgs -join "`n") | Should -Match '2 sessão.*-Forcar'
        $global:TU.D.Marca | Should -BeFalse
        Invoke-InstaladorTeste -MesmaPasta -Extra @{ Forcar = $true } | Should -Be 0
        $global:TU.D.Marca | Should -BeTrue
    }

    It 'E10 with --marcar exiting 7 says the bridge is still on' {
        $global:TU.D.Codigos['--marcar'] = 7
        Invoke-InstaladorTeste | Should -Be 1
        ($global:TU.Msgs -join "`n") | Should -Match 'ponte com o Windows continua ligada'
    }

    It 'Testar-E10 needs the marker and WSL_INTEROP unset' {
        Invoke-InstaladorTeste | Should -Be 0
        InModuleScope etapas { Testar-E10 } | Should -BeTrue
        $global:TU.D.Interop = $true
        InModuleScope etapas { Testar-E10 } | Should -BeFalse
        @($global:TU.Argvs | Where-Object { ($_ -join '|') -eq '-d|tune-up|--exec|/usr/bin/printenv|WSL_INTEROP' }).Count | Should -BeGreaterThan 0
    }
}

Describe 'Live-session lock' {
    BeforeEach {
        New-Maquina; Use-MaquinaFalsa
        InModuleScope etapas { $script:Fixados = @{ DISTRO = 'tune-up' }; $script:Opcoes = @{ Forcar = $false }; $script:ArquivoLog = $null }
    }

    It 'claude binary missing with /home/tuneup present => proceeds without asking for sessions' {
        $global:TU.D.Raiz = $true
        { InModuleScope etapas { Test-SessaoViva } } | Should -Not -Throw
        @($global:TU.Argvs | Where-Object { $_ -contains 'agents' }).Count | Should -Be 0
        @($global:TU.Argvs | Where-Object { ($_ -join '|') -eq '-d|tune-up|-u|tuneup|--exec|/usr/bin/test|-d|/home/tuneup' }).Count | Should -Be 1
    }

    It 'test -x exit 1 without /home/tuneup => refuses, -Forcar passes' {
        { InModuleScope etapas { Test-SessaoViva } } | Should -Throw '*Não consegui conferir*'
        @($global:TU.Argvs | Where-Object { $_ -contains 'agents' }).Count | Should -Be 0
        InModuleScope etapas { $script:Opcoes.Forcar = $true }
        { InModuleScope etapas { Test-SessaoViva } } | Should -Not -Throw
    }

    It 'only working/blocked/busy rows are live (<Nome>)' -ForEach @(
        @{ Nome = 'done and stopped'; Saida = '[{"state":"done"},{"state":"stopped"},{"state":"completed"},{"state":"finished","status":"stale"}]'; N = 0 }
        @{ Nome = 'done/completed/finished + idle is an open window'; Saida = '[{"state":"done","status":"idle"},{"state":"completed","status":"IDLE"},{"state":"finished","status":"idle"}]'; N = 3 }
        @{ Nome = 'non-object rows'; Saida = '[1,"x",null]'; N = 0 }
        @{ Nome = 'working'; Saida = '[{"state":"working"},{"state":"done"}]'; N = 1 }
        @{ Nome = 'blocked and waiting'; Saida = '[{"state":"blocked"},{"state":"done","status":"waiting"}]'; N = 2 }
        @{ Nome = 'status busy'; Saida = '[{"state":"done","status":"busy"}]'; N = 1 }
        @{ Nome = 'unknown state, not idle'; Saida = '[{"state":"novo"},{"state":"novo","status":"idle"}]'; N = 1 }
    ) {
        $global:TU.D.TesteClaude = 0; $global:TU.D.AgentsSaida = $Saida
        if ($N -eq 0) { { InModuleScope etapas { Test-SessaoViva } } | Should -Not -Throw }
        else { { InModuleScope etapas { Test-SessaoViva } } | Should -Throw "*Há $N sessão*" }
        @($global:TU.Argvs | Where-Object { ($_ -join '|') -like '*claude|agents|--json|--all' }).Count | Should -Be 1
    }

    It '<Nome> => proceeds' -ForEach @(@{ Nome = 'empty output'; Saida = '' }, @{ Nome = 'empty array'; Saida = " [ ]`n" }) {
        $global:TU.D.TesteClaude = 0; $global:TU.D.AgentsSaida = $Saida
        { InModuleScope etapas { Test-SessaoViva } } | Should -Not -Throw
    }

    It '<Nome> => refuses, -Forcar passes' -ForEach @(
        @{ Nome = 'a live session'; Codigo = 0; Saida = '[{"id":"x","status":"running"}]'; Erro = '*1 sessão*' }
        @{ Nome = 'agents --json failing'; Codigo = 1; Saida = ''; Erro = '*login pode ter expirado*' }
        @{ Nome = 'unparseable output'; Codigo = 0; Saida = 'Error: not logged in'; Erro = '*Não entendi*' }
        @{ Nome = 'a single JSON object'; Codigo = 0; Saida = '{"id":"x"}'; Erro = '*Não entendi*' }
        @{ Nome = 'a JSON string'; Codigo = 0; Saida = '"x"'; Erro = '*Não entendi*' }
        @{ Nome = 'test -x failing oddly'; Codigo = 0; Saida = ''; Teste = 255; Erro = '*Não consegui conferir*' }
    ) {
        $global:TU.D.TesteClaude = if ($Teste) { $Teste } else { 0 }
        $global:TU.D.AgentsCodigo = $Codigo; $global:TU.D.AgentsSaida = $Saida
        { InModuleScope etapas { Test-SessaoViva } } | Should -Throw $Erro
        InModuleScope etapas { $script:Opcoes.Forcar = $true }
        { InModuleScope etapas { Test-SessaoViva } } | Should -Not -Throw
        ($global:TU.Msgs -join "`n") | Should -Match '-Forcar'
    }
}

Describe 'E9 login' {
    BeforeEach { New-Maquina; Use-MaquinaFalsa; $global:TU.D.Auth = $false }

    It 'skips when auth status is 0' {
        $global:TU.D.Auth = $true
        Invoke-InstaladorTeste | Should -Be 0
        $global:TU.Terminais.Count | Should -Be 0
    }

    It 'opens the login terminal with the exact argv and waits' {
        $global:TU.LoginEm = $global:TU.Agora + 12
        Invoke-InstaladorTeste | Should -Be 0
        $global:TU.Terminais.Count | Should -Be 1
        ($global:TU.Terminais[0] -join '|') | Should -BeExactly 'C:\Windows\System32\wsl.exe|-d|tune-up|-u|tuneup|--cd|~|--exec|/usr/bin/env|BROWSER=/usr/local/bin/tune-up-abrir|/home/tuneup/.local/bin/claude|auth|login'
        Should -Invoke -ModuleName etapas Wait-Segundos -Times 3 -Exactly -ParameterFilter { $Segundos -eq 5 }
        $global:TU.D.Marca | Should -BeTrue
    }

    It 'times out after 15 minutes with the command to run again' {
        Invoke-InstaladorTeste | Should -Be 1
        $global:TU.Agora | Should -BeGreaterOrEqual 1900
        $global:TU.Agora | Should -BeLessThan 1910
        ($global:TU.Msgs -join "`n") | Should -Match '15 minutos.*powershell\.exe -NoProfile -ExecutionPolicy Bypass -File "C:\\tune-up\\scripts\\wsl\\instalar\.ps1"'
        (Get-Indice '--fechar') | Should -Be -1
    }

    It 'with -Projeto opens claude in that folder after login' {
        Mock -ModuleName etapas ConvertTo-CaminhoWsl { '/mnt/c/Users/Jo' + [char]0x00E3 + 'o Silva/site' }
        $proj = Join-Path $TestDrive 'site'; $null = New-Item -ItemType Directory -Force $proj
        $global:TU.LoginEm = $global:TU.Agora + 5
        Invoke-InstaladorTeste -Extra @{ Projeto = $proj } | Should -Be 0
        $global:TU.Terminais.Count | Should -Be 2
        ($global:TU.Terminais[1] -join '|') | Should -BeExactly ('C:\Windows\System32\wsl.exe|-d|tune-up|-u|tuneup|--cd|/mnt/c/Users/Jo' + [char]0x00E3 + 'o Silva/site|--exec|/home/tuneup/.local/bin/claude')
        $global:TU.Msgs | Should -Contain 'Abri o Claude na pasta do projeto: aceite a confiança na pasta e feche.'
    }

    It 'the -Projeto window opens only after --marcar, with the marker written and interop off (<Modo>)' -ForEach @(
        @{ Modo = 'full run'; Extra = @{} }
        @{ Modo = '-Login'; Extra = @{ Login = $true } }
        @{ Modo = 'login redone, E10 already done'; Extra = @{}; Antes = $true }
    ) {
        Mock -ModuleName etapas ConvertTo-CaminhoWsl { '/mnt/c/site' }
        $proj = Join-Path $TestDrive 'site'; $null = New-Item -ItemType Directory -Force $proj
        if ($Antes -or $Extra.Login) { $global:TU.D.Auth = $true; Invoke-InstaladorTeste | Should -Be 0; $global:TU.D.Auth = $false }
        $global:TU.Argvs.Clear(); $global:TU.Terminais.Clear(); $global:TU.LoginEm = $global:TU.Agora + 5
        $global:TU.NoTerminal = New-Object System.Collections.ArrayList
        Mock -ModuleName etapas Start-Terminal {
            $null = $global:TU.Terminais.Add([string[]]$Argv)
            $null = $global:TU.NoTerminal.Add(@{ N = $global:TU.Argvs.Count; Marca = $global:TU.D.Marca; Interop = $global:TU.D.Interop })
            $true
        }
        $e = @{ Projeto = $proj } + $Extra
        Invoke-InstaladorTeste -MesmaPasta:([bool]($Antes -or $Extra.Login)) -Extra $e | Should -Be 0
        $global:TU.Terminais.Count | Should -Be 2
        $global:TU.Terminais[1] | Should -Contain '--cd'
        $global:TU.Terminais[1][-1] | Should -Be '/home/tuneup/.local/bin/claude'
        $estado = $global:TU.NoTerminal[1]
        $estado.Marca | Should -BeTrue
        $estado.Interop | Should -BeFalse
        if (-not $Antes) {
            $m = -1
            for ($i = 0; $i -lt $global:TU.Argvs.Count; $i++) { if ($global:TU.Argvs[$i] -contains '--marcar') { $m = $i } }
            $m | Should -BeGreaterThan -1
            $estado.N | Should -BeGreaterThan $m
        }
    }

    It 'with -Projeto and the lock refusing at E10, the project window never opens' {
        Mock -ModuleName etapas ConvertTo-CaminhoWsl { '/mnt/c/site' }
        $proj = Join-Path $TestDrive 'site'; $null = New-Item -ItemType Directory -Force $proj
        $global:TU.LoginEm = $global:TU.Agora + 5; $global:TU.D.AgentsSaida = '[{"id":"a"}]'
        Invoke-InstaladorTeste -Extra @{ Projeto = $proj } | Should -Be 1
        $global:TU.Terminais.Count | Should -Be 1
    }
}

Describe 'E9 log hygiene (real Invoke-Wsl, fake wsl.exe)' {
    BeforeEach {
        New-Maquina
        Mock -ModuleName etapas Write-Mensagem { $null = $global:TU.Msgs.Add($Texto) }
        Mock -ModuleName etapas Start-Terminal { $true }
        Mock -ModuleName etapas Wait-Segundos { }
        Mock -ModuleName etapas Get-Agora { 1000 }
    }

    It 'the auth status output never reaches the log or the screen' {
        $falso = Join-Path $TestDrive 'wsl-auth.ps1'
        Set-Content -Path $falso -Value @('Write-Output "SEGREDO-AUTH pessoa@exemplo.com token-xyz"', 'exit 0')
        $global:TU.Falso = $falso
        Mock -ModuleName etapas Get-CaminhoWsl { $global:TU.Falso }
        $log = Join-Path $TestDrive 'auth.log'
        InModuleScope etapas -Parameters @{ L = $log } {
            param($L)
            $script:ArquivoLog = $L; $script:Fixados = @{ DISTRO = 'tune-up' }; $script:Opcoes = @{ Projeto = ''; Script = 'x' }
            Testar-E9 | Should -BeTrue
            Fazer-E9
            $script:ArquivoLog = $null
        }
        $texto = Get-Content -Raw $log
        $texto | Should -Match 'claude auth status => 0'
        $texto | Should -Not -Match 'SEGREDO-AUTH|token-xyz|exemplo'
        $global:TU.Msgs -join "`n" | Should -Not -Match 'SEGREDO-AUTH'
    }
}
