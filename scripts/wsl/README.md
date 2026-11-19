# Instalador do tune-up no Windows (WSL2)

Para quem vai rodar o instalador. Abra o PowerShell NORMAL (sem "Executar como administrador") na pasta do plugin e rode:

```
powershell -ExecutionPolicy Bypass -File scripts\wsl\instalar.ps1 -Projeto C:\caminho\do\projeto
```

O instalador cria uma distro Linux só dele, chamada `tune-up`. Ele pede permissão de administrador apenas se o Windows ainda não tiver o WSL, e pode pedir um reinício.

## Outros modos

- `-Login`: entra de novo na conta do Claude.
- `-Atualizar`: atualiza o que está dentro da distro.
- `-Medir`: só registra medidas para a prova em máquina real; não muda nada.
- `-Remover`: apaga a distro e a pasta do instalador, depois de você confirmar.
- `-Forcar`: segue mesmo com janelas do Claude abertas na distro (elas serão fechadas).
- `-SemReiniciar`: não reinicia o Windows sozinho; mostra o comando para continuar.
- `-Retomar`: continua depois de um reinício.
- Use só uma entre `-Remover`, `-Login`, `-Atualizar` e `-Medir`.

## Os 10 passos

1. Verifica o Windows.
2. Verifica se o WSL está instalado (instala se faltar).
3. Verifica se o Windows precisa reiniciar.
4. Atualiza o WSL.
5. Baixa o Ubuntu e confere o sha256.
6. Cria a distro `tune-up` (WSL 2).
7. Prepara o sistema da distro: pacotes, usuário `tuneup`, Node, FFmpeg.
8. Instala o Claude Code e o plugin, o Chrome e o HyperFrames.
9. Abre uma janela para você entrar na conta do Claude.
10. Confere tudo e fecha a ponte com o Windows; só então grava a marca `/etc/tune-up/pronto.json`.

## Códigos de saída

- 0: tudo certo (também quando só falta reiniciar).
- 1: falhou. Veja a mensagem e o log.
- 2: o instalador recusou rodar (por exemplo, como administrador, ou duas opções juntas).

## Log

`%LOCALAPPDATA%\tune-up\wsl\logs\instalar-AAAAMMDD-HHMMSS.log`. Ele guarda os comandos e os códigos de saída, não a saída dos comandos.

## Se der errado

- Virtualização desligada: ligue a virtualização (VT-x ou SVM) na BIOS e rode de novo.
- Reinício pendente: reinicie o Windows. Se o instalador não continuar sozinho, rode o comando acima com `-Retomar`.
- uid 1000: o Ubuntu baixado já trouxe um usuário com o número 1000. Rode com `-Remover` e peça ajuda ao suporte.
- Login expirado: rode com `-Login`.
- Janelas do Claude abertas na distro: feche-as, ou use `-Forcar`.
- Download recusado (sha256 diferente): verifique a internet e rode de novo. Nada baixado é usado antes de conferir.

Ainda não: o painel não abre ações do estúdio no Windows. Isso vem na próxima parte.
