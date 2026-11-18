# Pester 5: a failed -Retomar runs in the RunOnce console, which closes when powershell.exe exits.
BeforeAll {
    . (Join-Path $PSScriptRoot 'Comum.ps1')
    $script:LocalOriginal = $env:LOCALAPPDATA
}
AfterAll { $env:LOCALAPPDATA = $script:LocalOriginal; Remove-Variable -Name TU -Scope Global -ErrorAction SilentlyContinue }

Describe 'Failed resume stays visible' {
    BeforeEach { New-Maquina; Use-MaquinaFalsa }

    It 'logs the manual command and waits for Enter before the window closes' {
        $global:TU.Wsl = $false; $global:TU.ElevadoCodigo = 3010
        Invoke-InstaladorTeste | Should -Be 0
        $global:TU.Boot = 5000
        Mock -ModuleName etapas Invoke-Download { throw 'rede caiu' }
        Invoke-InstaladorTeste -MesmaPasta -Extra @{ Retomar = $true } | Should -Be 1
        $manual = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\tune-up\scripts\wsl\instalar.ps1" -Retomar'
        $logs = Get-ChildItem (Join-Path (Get-PastaTeste) 'logs') -Filter 'instalar-*.log'
        ($logs | ForEach-Object { Get-Content -Raw $_.FullName }) -join "`n" | Should -Match ([regex]::Escape($manual))
        Should -Invoke -ModuleName etapas Read-Resposta -Times 1 -Exactly -ParameterFilter { $Pergunta -match 'Enter' }
    }

    It 'a failure without -Retomar does not wait for Enter' {
        Mock -ModuleName etapas Invoke-Download { throw 'rede caiu' }
        Invoke-InstaladorTeste | Should -Be 1
        Should -Invoke -ModuleName etapas Read-Resposta -Times 0 -Exactly -ParameterFilter { $Pergunta -match 'Enter' }
    }
}
