# Pester 5 tests for -Login, -Atualizar, -Remover and the E1-E6 review leftovers.
BeforeAll {
    . (Join-Path $PSScriptRoot 'Comum.ps1')
    $script:LocalOriginal = $env:LOCALAPPDATA
    # One short label per in-distro call, consecutive repeats collapsed.
    function Get-Rotulos {
        $out = New-Object System.Collections.ArrayList
        foreach ($c in Get-ChamadasDistro) {
            $r = switch -Wildcard ($c) {
                '*/bin/rm|-f|/etc/tune-up/pronto.json' { 'rm-marca' }
                '*--abrir-interop' { 'abrir-interop' }
                '*/usr/bin/test|-x|/home/tuneup/.local/bin/claude' { 'lock' }
                '*agents|--json' { 'lock' }
                '--terminate|*' { 'terminate' }
                '*auth|status' { 'auth' }
                '*--verificar*' { 'verificar' }
                '*--fechar' { 'fechar' }
                '*--marcar*' { 'marcar' }
                '*/usr/bin/install*' { 'copia' }
                '*--usuario*' { 'usuario' }
                '--unregister|*' { 'unregister' }
                default { $c }
            }
            if ($out.Count -eq 0 -or $out[-1] -ne $r) { $null = $out.Add($r) }
        }
        return ($out -join ',')
    }
    function Invoke-Pronto { Invoke-InstaladorTeste | Should -Be 0; $global:TU.Argvs.Clear(); $global:TU.Msgs.Clear() }
}
AfterAll { $env:LOCALAPPDATA = $script:LocalOriginal; Remove-Variable -Name TU -Scope Global -ErrorAction SilentlyContinue }

Describe '-Login' {
    BeforeEach { New-Maquina; Use-MaquinaFalsa }

    It 'deletes the marker, opens interop, locks, terminates, logs in, then closes again' {
        Invoke-Pronto
        $global:TU.D.Auth = $false; $global:TU.LoginEm = $global:TU.Agora + 5
        Invoke-InstaladorTeste -MesmaPasta -Extra @{ Login = $true } | Should -Be 0
        Get-Rotulos | Should -Be 'rm-marca,abrir-interop,lock,terminate,auth,verificar,fechar,lock,terminate,marcar'
        $global:TU.Terminais.Count | Should -Be 1
        $global:TU.D.Marca | Should -BeTrue
        $global:TU.D.Interop | Should -BeFalse
    }

    It 'refuses when the distro is not installed' {
        Invoke-InstaladorTeste -Extra @{ Login = $true } | Should -Be 1
        @(Get-ArgvsDeEscrita).Count | Should -Be 0
    }
}

Describe '-Atualizar' {
    BeforeEach { New-Maquina; Use-MaquinaFalsa }

    It 'only copies, reinstalls the plugin and marks' {
        Invoke-Pronto
        $global:TU.D.Plugin = '0.0.1'
        Invoke-InstaladorTeste -MesmaPasta -Extra @{ Atualizar = $true } | Should -Be 0
        $escritas = @(Get-ArgvsDeEscrita | ForEach-Object { $_ -join '|' })
        @($escritas | Where-Object { $_ -notmatch '/usr/bin/install|--usuario|--marcar' }).Count | Should -Be 0
        @($escritas | Where-Object { $_ -match '--marcar' }).Count | Should -Be 1
        Get-Rotulos | Should -Be 'copia,usuario,marcar'
        $global:TU.D.Plugin | Should -Be $VersaoPluginReal
    }

    It '--marcar exiting 7 points to -Login or the full installer' {
        Invoke-Pronto
        $global:TU.D.Interop = $true
        Invoke-InstaladorTeste -MesmaPasta -Extra @{ Atualizar = $true } | Should -Be 1
        ($global:TU.Msgs -join "`n") | Should -Match '-Login.*instalador completo'
        @(Get-ChamadasDistro | Where-Object { $_ -match '--fechar|--terminate|--abrir-interop' }).Count | Should -Be 0
    }
}

Describe '-Remover' {
    BeforeEach { New-Maquina; Use-MaquinaFalsa }

    It 'without the typed confirmation does nothing' {
        Invoke-Pronto
        $global:TU.Resposta = 'sim'
        Invoke-InstaladorTeste -MesmaPasta -Extra @{ Remover = $true } | Should -Be 1
        @($global:TU.Argvs | Where-Object { $_[0] -eq '--unregister' }).Count | Should -Be 0
        Test-Path (Get-PastaTeste) | Should -BeTrue
        ($global:TU.Msgs -join "`n") | Should -Match 'Nada foi apagado'
    }

    It 'confirmed: locks, unregisters, removes RunOnce and the folder' {
        Invoke-Pronto
        $global:TU.Resposta = 'tune-up'
        Invoke-InstaladorTeste -MesmaPasta -Extra @{ Remover = $true } | Should -Be 0
        Get-Rotulos | Should -Be 'lock,unregister'
        Should -Invoke -ModuleName etapas Remove-RunOnce -Times 1 -Exactly
        Test-Path (Get-PastaTeste) | Should -BeFalse
        Test-Path (Join-Path $env:LOCALAPPDATA 'tune-up') | Should -BeTrue
    }

    It 'refuses a <Campo> mismatch' -ForEach @(@{ Campo = 'GUID'; G = '{outro}'; B = $null }, @{ Campo = 'BasePath'; G = $null; B = 'C:\outra' }) {
        Invoke-Pronto
        if ($G) { $global:TU.Reg.Guid = $G }
        if ($B) { $global:TU.Reg.BasePath = $B }
        $global:TU.Resposta = 'tune-up'
        Invoke-InstaladorTeste -MesmaPasta -Extra @{ Remover = $true } | Should -Be 1
        @($global:TU.Argvs | Where-Object { $_[0] -eq '--unregister' }).Count | Should -Be 0
        Test-Path (Get-PastaTeste) | Should -BeTrue
    }

    It 'without estado.json needs -Forcar and a BasePath inside our distro folder' {
        $env:LOCALAPPDATA = Join-Path $TestDrive ([guid]::NewGuid().ToString('N'))
        $global:TU.Distros = @('tune-up'); $global:TU.Resposta = 'tune-up'
        $global:TU.Reg = [pscustomobject]@{ Guid = '{x}'; BasePath = (Join-Path (Get-PastaTeste) 'distro') }
        Invoke-InstaladorTeste -MesmaPasta -Extra @{ Remover = $true } | Should -Be 1
        ($global:TU.Msgs -join "`n") | Should -Match '-Forcar'
        $global:TU.Reg.BasePath = 'C:\outra'
        Invoke-InstaladorTeste -MesmaPasta -Extra @{ Remover = $true; Forcar = $true } | Should -Be 1
        @($global:TU.Argvs | Where-Object { $_[0] -eq '--unregister' }).Count | Should -Be 0
        $global:TU.Reg.BasePath = (Join-Path (Get-PastaTeste) 'distro')
        Invoke-InstaladorTeste -MesmaPasta -Extra @{ Remover = $true; Forcar = $true } | Should -Be 0
        @($global:TU.Argvs | Where-Object { $_[0] -eq '--unregister' }).Count | Should -Be 1
    }

    It 'a link inside the folder refuses before --unregister and deletes nothing' {
        Invoke-Pronto
        $alvo = Join-Path $TestDrive 'fora'; $null = New-Item -ItemType Directory -Force $alvo
        Set-Content (Join-Path $alvo 'nao-apagar.txt') 'x'
        $null = New-Item -ItemType SymbolicLink -Path (Join-Path (Get-PastaTeste) 'baixados/link') -Target $alvo
        $global:TU.Resposta = 'tune-up'
        Invoke-InstaladorTeste -MesmaPasta -Extra @{ Remover = $true } | Should -Be 1
        ($global:TU.Msgs -join "`n") | Should -Match 'atalho'
        @($global:TU.Argvs | Where-Object { $_[0] -eq '--unregister' }).Count | Should -Be 0
        Test-Path (Join-Path $alvo 'nao-apagar.txt') | Should -BeTrue
        Test-Path (Join-Path (Get-PastaTeste) 'estado.json') | Should -BeTrue
    }

    It 'a live session refuses before --unregister' {
        Invoke-Pronto
        $global:TU.D.AgentsSaida = '[{"id":"a"}]'; $global:TU.Resposta = 'tune-up'
        Invoke-InstaladorTeste -MesmaPasta -Extra @{ Remover = $true } | Should -Be 1
        @($global:TU.Argvs | Where-Object { $_[0] -eq '--unregister' }).Count | Should -Be 0
    }
}

Describe 'Review leftovers of E1-E6' {
    BeforeEach { New-Maquina; Use-MaquinaFalsa }

    It 'refuses to run elevated with exit 2 and calls nothing' {
        $global:TU.Admin = $true
        Invoke-InstaladorTeste | Should -Be 2
        ($global:TU.Msgs -join "`n") | Should -Match 'administrador'
        Should -Invoke -ModuleName etapas Invoke-Wsl -Times 0 -Exactly
    }

    It 'E6 rechecks the rootfs hash on a resume that skips E5' {
        $env:LOCALAPPDATA = Join-Path $TestDrive ([guid]::NewGuid().ToString('N'))
        $b = Join-Path (Get-PastaTeste) 'baixados'; $null = New-Item -ItemType Directory -Force $b
        $arq = Join-Path $b 'ubuntu-24.04.5-wsl-amd64.wsl'
        [IO.File]::WriteAllText($arq, 'adulterado')
        [IO.File]::WriteAllText((Join-Path (Get-PastaTeste) 'estado.json'), '{"versao":1,"etapa":6}')
        Invoke-InstaladorTeste -MesmaPasta -Extra @{ Retomar = $true } | Should -Be 1
        Test-Path $arq | Should -BeFalse
        @($global:TU.Argvs | Where-Object { $_[0] -eq '--import' }).Count | Should -Be 0
    }

    It 'E6 saves importandoEm and the distro dir before importing' {
        $global:TU.ImportCodigo = -1; $global:TU.ImportSaida = 'outro erro'
        Invoke-InstaladorTeste | Should -Be 1
        $est = Get-Content -Raw (Join-Path (Get-PastaTeste) 'estado.json') | ConvertFrom-Json
        $est.importandoEm | Should -Be 1000
        $est.importandoDir | Should -Be (Join-Path (Get-PastaTeste) 'distro')
    }

    It 'E6 adopts a distro whose import was cut off before the GUID was saved' {
        $env:LOCALAPPDATA = Join-Path $TestDrive ([guid]::NewGuid().ToString('N'))
        $dir = Join-Path (Get-PastaTeste) 'distro'; $null = New-Item -ItemType Directory -Force $dir
        $j = @{ versao = 1; etapa = 6; importandoEm = 900; importandoDir = $dir } | ConvertTo-Json
        [IO.File]::WriteAllText((Join-Path (Get-PastaTeste) 'estado.json'), $j)
        $global:TU.Distros = @('tune-up'); $global:TU.Reg = [pscustomobject]@{ Guid = '{cccc}'; BasePath = $dir }
        Invoke-InstaladorTeste -MesmaPasta | Should -Be 0
        @($global:TU.Argvs | Where-Object { $_[0] -eq '--import' }).Count | Should -Be 0
        (Get-Content -Raw (Join-Path (Get-PastaTeste) 'estado.json') | ConvertFrom-Json).distroGuid | Should -Be '{cccc}'
    }

    It 'E6 does not adopt when the registry BasePath is elsewhere' {
        $env:LOCALAPPDATA = Join-Path $TestDrive ([guid]::NewGuid().ToString('N'))
        $dir = Join-Path (Get-PastaTeste) 'distro'; $null = New-Item -ItemType Directory -Force $dir
        [IO.File]::WriteAllText((Join-Path (Get-PastaTeste) 'estado.json'), (@{ versao = 1; importandoEm = 900; importandoDir = $dir } | ConvertTo-Json))
        $global:TU.Distros = @('tune-up'); $global:TU.Reg = [pscustomobject]@{ Guid = '{cccc}'; BasePath = 'C:\outra' }
        Invoke-InstaladorTeste -MesmaPasta | Should -Be 1
        ($global:TU.Msgs -join "`n") | Should -Match 'não foi criada por este instalador'
    }

    It 'Assert-Argv refuses a double quote and a trailing backslash, accepts spaces and accents' {
        { InModuleScope etapas { Assert-Argv @('a"b') } } | Should -Throw '*aspas*'
        { InModuleScope etapas { Assert-Argv @('C:\pasta\') } } | Should -Throw '*aspas*'
        $nome = "C:\Users\Jo$([char]0x00E3)o Silva"
        { InModuleScope etapas -Parameters @{ N = $nome } { param($N) Assert-Argv @($N, '/mnt/c/a b') } } | Should -Not -Throw
    }

    It 'E4 that only warned prints aviso, not ok' {
        $global:TU.UpdateCodigo = 1; $global:TU.UpdateSaida = 'network'
        Invoke-InstaladorTeste | Should -Be 0
        @($global:TU.Msgs | Where-Object { $_ -like '`[4/10`]*' }) | Should -Be @('[4/10] Atualizando o WSL... aviso')
    }

    It 'a failing wsl -l -q is logged with its exit code' {
        $global:TU.ListaCodigo = 5
        Invoke-InstaladorTeste | Should -Be 0
        (Get-ChildItem (Join-Path (Get-PastaTeste) 'logs') | Get-Content -Raw) | Should -Match 'wsl -l -q saiu com codigo 5'
    }

    It 'a failed -Retomar still waits for Enter when Write-Log throws' {
        $global:TU.Wsl = $false; $global:TU.ElevadoCodigo = 3010
        Invoke-InstaladorTeste | Should -Be 0
        $global:TU.Boot = 5000
        Mock -ModuleName etapas Write-Log { throw 'disco cheio' }
        { Invoke-InstaladorTeste -MesmaPasta -Extra @{ Retomar = $true } } | Should -Throw '*disco cheio*'
        Should -Invoke -ModuleName etapas Read-Resposta -Times 1 -Exactly -ParameterFilter { $Pergunta -match 'Enter' }
    }
}

Describe 'Start-Terminal' {
    BeforeEach {
        New-Maquina
        $global:TU.SystemRoot = $env:SystemRoot; $env:SystemRoot = 'C:\Windows'
        Mock -ModuleName etapas Start-Process { $global:TU.Inicio = @{ Arquivo = $FilePath; Args = @($ArgumentList) } }
    }
    AfterEach { $env:SystemRoot = $global:TU.SystemRoot }

    It 'uses wt.exe new-tab with the argv, quoting elements with spaces' {
        Mock -ModuleName etapas Get-Command -ParameterFilter { $Name -eq 'wt.exe' } { [pscustomobject]@{ Name = 'wt.exe' } }
        InModuleScope etapas { Start-Terminal -Argv @('C:\Windows\System32\wsl.exe', '--cd', '/mnt/c/a b', '--exec', 'x') } | Should -BeTrue
        $global:TU.Inicio.Arquivo | Should -Be 'wt.exe'
        ($global:TU.Inicio.Args -join '|') | Should -BeExactly '-w|0|nt|C:\Windows\System32\wsl.exe|--cd|"/mnt/c/a b"|--exec|x'
    }

    It 'falls back to cmd start without wt.exe' {
        Mock -ModuleName etapas Get-Command -ParameterFilter { $Name -eq 'wt.exe' } { $null }
        InModuleScope etapas { Start-Terminal -Argv @('C:\Windows\System32\wsl.exe', '-d', 'tune-up') } | Should -BeTrue
        $global:TU.Inicio.Arquivo | Should -Be 'C:\Windows\System32\cmd.exe'
        ($global:TU.Inicio.Args -join '|') | Should -BeExactly '/c|start|""|C:\Windows\System32\wsl.exe|-d|tune-up'
    }

    It 'refuses a cmd/wt metacharacter (<C>) and opens nothing' -ForEach @(@{ C = '&' }, @{ C = ';' }, @{ C = '%' }, @{ C = '(' }) {
        Mock -ModuleName etapas Get-Command -ParameterFilter { $Name -eq 'wt.exe' } { $null }
        InModuleScope etapas -Parameters @{ C = $C } { param($C) Start-Terminal -Argv @('wsl.exe', "/mnt/c/a${C}b") } | Should -BeFalse
        Should -Invoke -ModuleName etapas Start-Process -Times 0 -Exactly
    }
}
