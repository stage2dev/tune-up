# Pester 5 tests for instalar.ps1 / etapas.psm1, steps E1 to E6. Windows-only cases are skipped elsewhere.
BeforeAll {
    . (Join-Path $PSScriptRoot 'Comum.ps1')
    $script:LocalOriginal = $env:LOCALAPPDATA
}
AfterAll { $env:LOCALAPPDATA = $script:LocalOriginal; Remove-Variable -Name TU -Scope Global -ErrorAction SilentlyContinue }

Describe 'Runner E1..E6' {
    BeforeEach { New-Maquina; Use-MaquinaFalsa }

    It 'runs E1..E10 in order and imports with the exact argv' {
        $global:TU.Wsl = $false
        Invoke-InstaladorTeste | Should -Be 0
        $linhas = @($global:TU.Msgs | Where-Object { $_ -match '^\[\d+/10\]' })
        ($linhas | ForEach-Object { [int]($_ -replace '^\[(\d+)/10\].*', '$1') }) -join ',' | Should -Be '1,2,3,4,5,6,7,8,9,10'
        @($linhas[6..9] | Where-Object { $_ -match '\.\.\. ok' }).Count | Should -Be 4
        $dir = Join-Path (Get-PastaTeste) 'distro'
        $rootfs = Join-Path (Join-Path (Get-PastaTeste) 'baixados') 'ubuntu-24.04.5-wsl-amd64.wsl'
        $imp = @($global:TU.Argvs | Where-Object { $_[0] -eq '--import' })
        $imp.Count | Should -Be 1
        ($imp[0] -join '|') | Should -Be ("--import|tune-up|$dir|$rootfs|--version|2")
        $est = Get-Content -Raw (Join-Path (Get-PastaTeste) 'estado.json') | ConvertFrom-Json
        $est.distroGuid | Should -Be '{1111-2222}'
        $est.distroBasePath | Should -Be $dir
        $est.etapa | Should -Be 11
    }

    It 'a second run with everything done makes zero write calls' {
        Invoke-InstaladorTeste | Should -Be 0
        $estado = Join-Path (Get-PastaTeste) 'estado.json'
        $antes = (Get-FileHash $estado).Hash
        $quando = (Get-Item $estado).LastWriteTimeUtc
        $global:TU.Argvs.Clear(); $global:TU.Elevados.Clear()
        Invoke-InstaladorTeste -MesmaPasta | Should -Be 0
        @(Get-ArgvsDeEscrita).Count | Should -Be 0
        $global:TU.Elevados.Count | Should -Be 0
        Should -Invoke -ModuleName etapas Invoke-Download -Times 1 -Exactly
        Should -Invoke -ModuleName etapas Set-RunOnce -Times 0 -Exactly
        (Get-FileHash $estado).Hash | Should -Be $antes
        (Get-Item $estado).LastWriteTimeUtc | Should -Be $quando
        @($global:TU.Msgs | Where-Object { $_ -match '^\[([2-9]|10)/10\].*já estava pronto' }).Count | Should -Be 9
        $global:TU.Terminais.Count | Should -Be 0
    }

    It 'E1 without virtualization stops with a BIOS instruction and never calls wsl' {
        $global:TU.Hyper = $false; $global:TU.VirtFw = $false
        Invoke-InstaladorTeste | Should -Be 1
        ($global:TU.Msgs -join "`n") | Should -Match 'BIOS/UEFI'
        Should -Invoke -ModuleName etapas Invoke-Wsl -Times 0 -Exactly
        Should -Invoke -ModuleName etapas Invoke-WslElevado -Times 0 -Exactly
    }

    It 'E1 with hypervisor present ignores the firmware flag' {
        $global:TU.VirtFw = $false; Invoke-InstaladorTeste | Should -Be 0
    }

    It 'refuses ARM64 without calling wsl' {
        $global:TU.Arch = 12
        Invoke-InstaladorTeste | Should -Be 1
        ($global:TU.Msgs -join "`n") | Should -Match 'ARM64'
        Should -Invoke -ModuleName etapas Invoke-Wsl -Times 0 -Exactly
    }

    It 'refuses less than 12 GB free' {
        $global:TU.Livre = 5GB
        Invoke-InstaladorTeste | Should -Be 1
        ($global:TU.Msgs -join "`n") | Should -Match '12 GB'
    }

    It 'refuses an empty LOCALAPPDATA with exit code 2' {
        $env:LOCALAPPDATA = ''
        $fx = New-FixadosTeste (Join-Path $TestDrive 'fixados.env')
        Invoke-Instalador -Fixados $fx -Script 'C:\x\instalar.ps1' | Should -Be 2
        ($global:TU.Msgs -join "`n") | Should -Match 'LOCALAPPDATA'
    }

    It '-Medir exits 2 with the not-implemented message; two modes at once exit 2' {
        Invoke-Instalador -Medir | Should -Be 2
        $global:TU.Msgs[0] | Should -Be 'ainda nao implementado nesta versao'
        Invoke-Instalador -Login -Remover | Should -Be 2
        $global:TU.Msgs[1] | Should -Match 'só uma opção'
    }

    It 'E2 with WSL missing elevates exactly --install --no-distribution' {
        $global:TU.Wsl = $false
        Invoke-InstaladorTeste | Should -Be 0
        @($global:TU.Elevados) | Should -Be @('--install --no-distribution')
        (Get-Content -Raw (Join-Path (Get-PastaTeste) 'estado.json') | ConvertFrom-Json).wslInstalarCodigo | Should -Be 0
    }

    It 'E2 with UAC cancelled stops with a clear message and goes no further' {
        $global:TU.Wsl = $false; $global:TU.InstalarLiga = $false; $global:TU.ElevadoCodigo = 1223
        Invoke-InstaladorTeste | Should -Be 1
        ($global:TU.Msgs -join "`n") | Should -Match 'permissão de administrador foi recusada'
        @($global:TU.Msgs | Where-Object { $_ -like '`[3/10`]*' }).Count | Should -Be 0
    }

    It 'no argv ever contains a bare double dash' {
        $global:TU.Wsl = $false
        Invoke-InstaladorTeste | Should -Be 0
        $global:TU.Argvs.Count | Should -BeGreaterThan 3
        foreach ($a in $global:TU.Argvs) { $a | Should -Not -Contain '--' }
    }
}

Describe 'E3 reboot' {
    BeforeEach { New-Maquina; Use-MaquinaFalsa }

    It 'reboots on <Nome>' -ForEach @(
        @{ Nome = 'wsl --version still failing after install'; Prep = { $global:TU.Wsl = $false; $global:TU.InstalarLiga = $false }; Etapa = 3 }
        @{ Nome = 'exit code 3010'; Prep = { $global:TU.Wsl = $false; $global:TU.ElevadoCodigo = 3010 }; Etapa = 3 }
        @{ Nome = 'exit code 1641'; Prep = { $global:TU.Wsl = $false; $global:TU.ElevadoCodigo = 1641 }; Etapa = 3 }
        @{ Nome = 'HKLM keys plus WSL just installed'; Prep = { $global:TU.Wsl = $false; $global:TU.Hklm = $true }; Etapa = 3 }
        @{ Nome = 'import failing with a VM-platform error'; Prep = { $global:TU.ImportCodigo = -1; $global:TU.ImportSaida = 'Error code: Wsl/Service/RegisterDistro/HCS_E_HYPERV_NOT_INSTALLED' }; Etapa = 6 }
    ) {
        & $Prep
        Invoke-InstaladorTeste | Should -Be 0
        $global:TU.RunOnce | Should -Be 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\tune-up\scripts\wsl\instalar.ps1" -Retomar'
        (Get-Content -Raw (Join-Path (Get-PastaTeste) 'estado.json') | ConvertFrom-Json).etapa | Should -Be $Etapa
        @($global:TU.Msgs | Where-Object { $_ -match '^\[(\d+)/10\]' -and [int]$Matches[1] -gt $Etapa }).Count | Should -Be 0
        Should -Invoke -ModuleName etapas Read-Resposta -Times 1 -Exactly
    }

    It 'HKLM keys alone on a machine with working WSL do not reboot' {
        $global:TU.Hklm = $true
        Invoke-InstaladorTeste | Should -Be 0
        Should -Invoke -ModuleName etapas Set-RunOnce -Times 0 -Exactly
        @($global:TU.Msgs | Where-Object { $_ -like '`[6/10`]*ok' }).Count | Should -Be 1
    }

    It 'HKLM keys after the machine already booted since the install do not reboot again' {
        $global:TU.Wsl = $false; $global:TU.Hklm = $true; $global:TU.Boot = 2000
        Invoke-InstaladorTeste | Should -Be 0
        Should -Invoke -ModuleName etapas Set-RunOnce -Times 0 -Exactly
    }

    It 'a RunOnce command over 260 characters is not written and the manual command is shown' {
        $global:TU.Wsl = $false; $global:TU.ElevadoCodigo = 3010
        $env:LOCALAPPDATA = Join-Path $TestDrive ([guid]::NewGuid().ToString('N'))
        $fx = New-FixadosTeste (Join-Path $TestDrive 'fixados.env')
        $longo = 'C:\' + ('p' * 250) + '\instalar.ps1'
        Invoke-Instalador -Fixados $fx -Script $longo -SemReiniciar | Should -Be 0
        Should -Invoke -ModuleName etapas Set-RunOnce -Times 0 -Exactly
        $global:TU.Msgs | Should -Contain ('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}" -Retomar' -f $longo)
    }

    It '-SemReiniciar never asks and never restarts' {
        $global:TU.Wsl = $false; $global:TU.ElevadoCodigo = 3010; $global:TU.Resposta = 's'
        Invoke-InstaladorTeste -Extra @{ SemReiniciar = $true } | Should -Be 0
        Should -Invoke -ModuleName etapas Read-Resposta -Times 0 -Exactly
        Should -Invoke -ModuleName etapas Invoke-ReiniciarWindows -Times 0 -Exactly
    }

    It 'answering s restarts once' {
        $global:TU.Wsl = $false; $global:TU.ElevadoCodigo = 3010; $global:TU.Resposta = 's'
        Invoke-InstaladorTeste | Should -Be 0
        Should -Invoke -ModuleName etapas Invoke-ReiniciarWindows -Times 1 -Exactly
    }

    It '-Retomar removes RunOnce and continues from the saved step' {
        $global:TU.Wsl = $false; $global:TU.ElevadoCodigo = 3010
        Invoke-InstaladorTeste | Should -Be 0
        $global:TU.Boot = 5000
        $global:TU.RunOnce = 'ainda-la'
        Invoke-InstaladorTeste -MesmaPasta -Extra @{ Retomar = $true } | Should -Be 0
        Should -Invoke -ModuleName etapas Remove-RunOnce -Times 1 -Exactly
        $global:TU.RunOnce | Should -BeNullOrEmpty
        $nums = @($global:TU.Msgs | Where-Object { $_ -match '^\[(\d+)/10\]' } | ForEach-Object { [int]($_ -replace '^\[(\d+)/10\].*', '$1') })
        $nums[0] | Should -Be 3
        $nums | Should -Contain 6
    }

    It 'a failed resume shows the exact command to run by hand' {
        $global:TU.Wsl = $false; $global:TU.ElevadoCodigo = 3010
        Invoke-InstaladorTeste | Should -Be 0
        $global:TU.Boot = 5000
        Mock -ModuleName etapas Invoke-Download { throw 'rede caiu' }
        Invoke-InstaladorTeste -MesmaPasta -Extra @{ Retomar = $true } | Should -Be 1
        $global:TU.Msgs | Should -Contain 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\tune-up\scripts\wsl\instalar.ps1" -Retomar'
    }

    It 'a second VM-platform failure after a reboot stops instead of looping' {
        $global:TU.ImportCodigo = -1; $global:TU.ImportSaida = '0x80370102'
        Invoke-InstaladorTeste | Should -Be 0
        $global:TU.Boot = 5000
        Invoke-InstaladorTeste -MesmaPasta -Extra @{ Retomar = $true } | Should -Be 1
        ($global:TU.Msgs -join "`n") | Should -Match 'Plataforma de Máquina Virtual'
    }
}

Describe 'E4 update' {
    BeforeEach { New-Maquina; Use-MaquinaFalsa }

    It 'access denied elevates only wsl --update' {
        $global:TU.UpdateCodigo = 5
        Invoke-InstaladorTeste | Should -Be 0
        @($global:TU.Elevados) | Should -Be @('--update')
    }

    It 'a network failure is only a warning when wsl --version works' {
        $global:TU.UpdateCodigo = 1; $global:TU.UpdateSaida = 'network'
        Invoke-InstaladorTeste | Should -Be 0
        ($global:TU.Msgs -join "`n") | Should -Match 'Aviso'
        $global:TU.Elevados.Count | Should -Be 0
    }
}

Describe 'E5 rootfs' {
    BeforeEach { New-Maquina; Use-MaquinaFalsa }

    It 'a wrong sha256 deletes the file and stops' {
        $global:TU.Conteudo = 'adulterado'
        Invoke-InstaladorTeste | Should -Be 1
        ($global:TU.Msgs -join "`n") | Should -Match 'não confere'
        Test-Path (Join-Path (Join-Path (Get-PastaTeste) 'baixados') 'ubuntu-24.04.5-wsl-amd64.wsl') | Should -BeFalse
        @($global:TU.Argvs | Where-Object { $_[0] -eq '--import' }).Count | Should -Be 0
    }

    It 'the right file already on disk is not downloaded again' {
        $env:LOCALAPPDATA = Join-Path $TestDrive ([guid]::NewGuid().ToString('N'))
        $b = Join-Path (Get-PastaTeste) 'baixados'
        $null = New-Item -ItemType Directory -Force $b
        [IO.File]::WriteAllText((Join-Path $b 'ubuntu-24.04.5-wsl-amd64.wsl'), 'conteudo-ubuntu')
        Invoke-InstaladorTeste -MesmaPasta | Should -Be 0
        Should -Invoke -ModuleName etapas Invoke-Download -Times 0 -Exactly
    }
}

Describe 'E6 distro ownership' {
    BeforeEach {
        New-Maquina; Use-MaquinaFalsa
        $global:TU.Distros = @('Ubuntu', 'tune-up')
        $global:TU.Reg = [pscustomobject]@{ Guid = '{aaaa}'; BasePath = 'C:\base' }
    }

    It 'present without estado.json stops untouched' {
        InModuleScope etapas {
            $script:Fixados = @{ DISTRO = 'tune-up' }
            $script:EstadoExistia = $false
            $script:Estado = @{ distroGuid = '{aaaa}'; distroBasePath = 'C:\base' }
            { Testar-E6 } | Should -Throw '*Já existe uma distro tune-up que não foi criada por este instalador*'
        }
    }

    It 'present with a different <Campo> stops untouched' -ForEach @(
        @{ Campo = 'GUID'; Guid = '{bbbb}'; Base = 'C:\base' }
        @{ Campo = 'BasePath'; Guid = '{aaaa}'; Base = 'C:\outra' }
    ) {
        InModuleScope etapas -Parameters @{ G = $Guid; B = $Base } {
            param($G, $B)
            $script:Fixados = @{ DISTRO = 'tune-up' }
            $script:EstadoExistia = $true
            $script:Estado = @{ distroGuid = $G; distroBasePath = $B }
            { Testar-E6 } | Should -Throw '*não foi criada por este instalador*'
        }
    }

    It 'a full run with a foreign tune-up never imports or removes anything' {
        Invoke-InstaladorTeste | Should -Be 1
        @(Get-ArgvsDeEscrita | Where-Object { $_[0] -ne '--update' }).Count | Should -Be 0
    }

    It 'ours is skipped' {
        InModuleScope etapas {
            $script:Fixados = @{ DISTRO = 'tune-up' }
            $script:EstadoExistia = $true
            $script:Estado = @{ distroGuid = '{aaaa}'; distroBasePath = 'C:\base' }
            Testar-E6 | Should -BeTrue
        }
        @($global:TU.Argvs | Where-Object { $_[0] -eq '--import' }).Count | Should -Be 0
    }

    It 'version 1 after import is set to 2' {
        $global:TU.Distros = @(); $global:TU.Reg = $null; $global:TU.Versao = '1'
        Invoke-InstaladorTeste | Should -Be 0
        @($global:TU.Argvs | Where-Object { ($_ -join ' ') -eq '--set-version tune-up 2' }).Count | Should -Be 1
    }

    It 'a non-VM import failure stops with the log path and no reboot' {
        $global:TU.Distros = @(); $global:TU.Reg = $null; $global:TU.ImportCodigo = -1; $global:TU.ImportSaida = 'outro erro'
        Invoke-InstaladorTeste | Should -Be 1
        Should -Invoke -ModuleName etapas Set-RunOnce -Times 0 -Exactly
        ($global:TU.Msgs -join "`n") | Should -Match 'Não consegui criar a distro'
    }
}

Describe 'Read-Fixados' {
    BeforeAll {
        $script:Base = [IO.File]::ReadAllText((Join-Path $RaizWsl 'fixados.env'))
        function Test-Fixados([string]$Texto) {
            $f = Join-Path $TestDrive 'fx.env'
            [IO.File]::WriteAllText($f, $Texto, (New-Object Text.UTF8Encoding $false))
            InModuleScope etapas -Parameters @{ F = $f } { param($F) Read-Fixados -Caminho $F }
        }
    }

    It 'accepts the real file' { (Test-Fixados $script:Base).DISTRO | Should -Be 'tune-up' }

    It 'rejects <Nome>' -ForEach @(
        @{ Nome = 'an unknown key'; De = 'USUARIO=tuneup'; Para = "USUARIO=tuneup`nEXTRA=1"; Erro = '*chave desconhecida EXTRA*' }
        @{ Nome = 'a duplicate key'; De = 'USUARIO=tuneup'; Para = "USUARIO=tuneup`nUSUARIO=outro"; Erro = '*chave repetida USUARIO*' }
        @{ Nome = 'a missing key'; De = 'USUARIO=tuneup'; Para = ''; Erro = '*faltam as chaves USUARIO*' }
        @{ Nome = 'command substitution'; De = 'USUARIO=tuneup'; Para = 'USUARIO=$(x)'; Erro = '*valor inválido em USUARIO*' }
        @{ Nome = 'a backtick'; De = 'USUARIO=tuneup'; Para = 'USUARIO=a`b'; Erro = '*valor inválido*' }
        @{ Nome = 'a space'; De = 'USUARIO=tuneup'; Para = 'USUARIO=a b'; Erro = '*valor inválido*' }
        @{ Nome = 'a quote'; De = 'USUARIO=tuneup'; Para = 'USUARIO="tuneup"'; Erro = '*valor inválido*' }
        @{ Nome = 'a semicolon'; De = 'USUARIO=tuneup'; Para = 'USUARIO=a;b'; Erro = '*valor inválido*' }
        @{ Nome = 'a lowercase key'; De = 'USUARIO=tuneup'; Para = 'usuario=tuneup'; Erro = '*CHAVE=valor*' }
        @{ Nome = 'CRLF'; De = 'USUARIO=tuneup'; Para = "USUARIO=tuneup`r"; Erro = '*LF*' }
    ) {
        { Test-Fixados ($script:Base.Replace($De, $Para)) } | Should -Throw $Erro
    }
}

Describe 'ConvertTo-CaminhoWsl' {
    BeforeEach { New-Maquina; Use-MaquinaFalsa }

    It 'translates <Entrada>' -ForEach @(
        @{ Entrada = 'C:\Users\x\proj'; Saida = '/mnt/c/Users/x/proj' }
        @{ Entrada = 'D:\Meus Projetos\a b\'; Saida = '/mnt/d/Meus Projetos/a b' }
        @{ Entrada = "C:\Users\Jo$([char]0x00E3)o Silva\site"; Saida = "/mnt/c/Users/Jo$([char]0x00E3)o Silva/site" }
        @{ Entrada = 'E:\'; Saida = '/mnt/e' }
    ) {
        InModuleScope etapas -Parameters @{ E = $Entrada } { param($E) ConvertTo-CaminhoWsl -Caminho $E } | Should -BeExactly $Saida
    }

    It 'refuses <Nome>' -ForEach @(
        @{ Nome = 'UNC'; Entrada = '\\servidor\pasta'; Erro = '*rede*' }
        @{ Nome = 'the \\?\ prefix'; Entrada = '\\?\C:\x'; Erro = '*\\?\*' }
        @{ Nome = 'a relative path'; Entrada = 'projeto\a'; Erro = '*caminho completo*' }
        @{ Nome = 'a drive-relative path'; Entrada = 'C:projeto'; Erro = '*caminho completo*' }
    ) {
        { InModuleScope etapas -Parameters @{ E = $Entrada } { param($E) ConvertTo-CaminhoWsl -Caminho $E } } | Should -Throw $Erro
    }

    It 'refuses a network drive' {
        $global:TU.TipoDisco = 4
        { InModuleScope etapas { ConvertTo-CaminhoWsl -Caminho 'Z:\x' } } | Should -Throw '*unidade de rede*'
    }
}

Describe 'Wrappers' {
    BeforeEach { New-Maquina }

    It 'Invoke-WslElevado targets the System32 wsl.exe' {
        $antes = $env:SystemRoot; $env:SystemRoot = 'C:\Windows'
        try {
            Mock -ModuleName etapas Start-ProcessoElevado { $global:TU.Alvo = $Arquivo; $global:TU.Args = $Argumentos; [pscustomobject]@{ ExitCode = 0 } | Add-Member -MemberType ScriptMethod -Name WaitForExit -Value { } -PassThru }
            InModuleScope etapas { Invoke-WslElevado -Argv @('--install', '--no-distribution') } | Should -Be 0
            $global:TU.Alvo | Should -BeExactly 'C:\Windows\System32\wsl.exe'
            $global:TU.Args | Should -BeExactly '--install --no-distribution'
        } finally { $env:SystemRoot = $antes }
    }

    It 'a cancelled UAC prompt returns 1223 with a clear message, no exception' {
        $antes = $env:SystemRoot; $env:SystemRoot = 'C:\Windows'
        try {
            Mock -ModuleName etapas Write-Mensagem { $null = $global:TU.Msgs.Add($Texto) }
            # The real exception type the ShellExecute launch throws when the UAC prompt is cancelled.
            Mock -ModuleName etapas Start-ProcessoElevado { throw (New-Object System.ComponentModel.Win32Exception 1223) }
            InModuleScope etapas { Invoke-WslElevado -Argv @('--update') } | Should -Be 1223
            ($global:TU.Msgs -join "`n") | Should -Match 'permissão de administrador foi recusada'
        } finally { $env:SystemRoot = $antes }
    }

    It 'Invoke-Wsl and Invoke-WslElevado refuse a bare double dash' {
        { InModuleScope etapas { Invoke-Wsl -Argv @('-d', 'tune-up', '--', 'id') } } | Should -Throw '*proibido*'
        { InModuleScope etapas { Invoke-WslElevado -Argv @('--') } } | Should -Throw '*proibido*'
    }

    It 'Invoke-Wsl sets WSL_UTF8 only for the call and the log never holds output or env' {
        $falso = Join-Path $TestDrive 'wsl-falso.ps1'
        Set-Content -Path $falso -Value @(
            'Write-Output "auth MARCADOR-SAIDA-AUTH"'
            'Write-Output "WSL_UTF8=$env:WSL_UTF8"'
            'Get-ChildItem env: | ForEach-Object { Write-Output ("{0}={1}" -f $_.Name, $_.Value) }'
            'exit 7')
        $env:TU_MARCADOR_ENV = 'MARCADOR-ENV-99'
        $antesUtf8 = $env:WSL_UTF8
        $log = Join-Path $TestDrive 'teste.log'
        try {
            $global:TU.Falso = $falso
            Mock -ModuleName etapas Get-CaminhoWsl { $global:TU.Falso }
            $r = InModuleScope etapas -Parameters @{ L = $log } {
                param($L)
                $script:ArquivoLog = $L; $script:EtapaAtual = 2
                $x = Invoke-Wsl -Utf8 -Argv @('--exec', 'claude', 'auth', 'status')
                Write-Log 'conta pessoa@exemplo.com'
                $script:ArquivoLog = $null
                $x
            }
        } finally { Remove-Item env:TU_MARCADOR_ENV }
        $r.Codigo | Should -Be 7
        $r.Saida | Should -Match 'WSL_UTF8=1'
        $env:WSL_UTF8 | Should -Be $antesUtf8
        $texto = Get-Content -Raw $log
        $texto | Should -Match '\[E2\] wsl.exe --exec claude auth status => 7'
        $texto | Should -Not -Match 'MARCADOR-SAIDA-AUTH'
        $texto | Should -Not -Match 'MARCADOR-ENV-99'
        $texto | Should -Not -Match 'pessoa@exemplo'
    }
}

Describe 'Encoding' {
    It '<Arquivo> is UTF-8 with BOM so PowerShell 5.1 keeps the accents' -ForEach @(
        @{ Arquivo = 'etapas.psm1' }, @{ Arquivo = 'apoio.ps1' }, @{ Arquivo = 'distro.ps1' }, @{ Arquivo = 'instalar.ps1' }
    ) {
        $b = [IO.File]::ReadAllBytes((Join-Path $RaizWsl $Arquivo))
        ($b[0], $b[1], $b[2]) -join ',' | Should -Be '239,187,191'
    }

    It 'pt-BR messages keep their accents after loading' {
        InModuleScope etapas { $script:Etapas[1].Texto } | Should -BeExactly ("Verificando se o WSL est$([char]0x00E1) instalado")
    }
}

Describe 'Registry helpers (Windows only)' -Skip:(-not $EhWindows) {
    BeforeEach {
        InModuleScope etapas { $script:RaizHkcu = 'TestRegistry:'; $script:RaizHklm = 'TestRegistry:\HKLM' }
    }
    AfterEach {
        InModuleScope etapas { $script:RaizHkcu = 'HKCU:'; $script:RaizHklm = 'HKLM:' }
    }

    It 'Get-DistroRegistrada reads GUID and BasePath of the tune-up subkey' {
        $k = 'TestRegistry:\Software\Microsoft\Windows\CurrentVersion\Lxss\{abcd}'
        $null = New-Item -Path $k -Force
        $null = New-ItemProperty -Path $k -Name DistributionName -Value 'tune-up'
        $null = New-ItemProperty -Path $k -Name BasePath -Value 'C:\d'
        $r = InModuleScope etapas { Get-DistroRegistrada -Nome 'tune-up' }
        $r.Guid | Should -Be '{abcd}'
        $r.BasePath | Should -Be 'C:\d'
    }

    It 'Set-RunOnce and Remove-RunOnce write and remove TuneUpWsl under HKCU' {
        InModuleScope etapas { Set-RunOnce -Comando 'x -Retomar' }
        (Get-ItemProperty 'TestRegistry:\Software\Microsoft\Windows\CurrentVersion\RunOnce').TuneUpWsl | Should -Be 'x -Retomar'
        InModuleScope etapas { Remove-RunOnce }
        (Get-ItemProperty 'TestRegistry:\Software\Microsoft\Windows\CurrentVersion\RunOnce').PSObject.Properties['TuneUpWsl'] | Should -BeNullOrEmpty
    }

    It 'Test-ReinicioPendenteHklm sees each key' {
        InModuleScope etapas { Test-ReinicioPendenteHklm } | Should -BeFalse
        $null = New-Item -Force -Path 'TestRegistry:\HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired'
        InModuleScope etapas { Test-ReinicioPendenteHklm } | Should -BeTrue
    }
}
