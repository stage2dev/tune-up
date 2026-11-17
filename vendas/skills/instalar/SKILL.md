---
name: instalar
description: "One-step setup of the WhatsApp sales screen on this computer: Docker, the local Evolution API and the sales service, step by step in plain words. Use on: install, set up WhatsApp, prepare sales; instalar, preparar, preparar o WhatsApp, setup WhatsApp, configurar vendas."
---

# Instalar (preparar o WhatsApp neste computador)

The owner is usually not technical. Speak plain pt-BR, one short sentence per step, no jargon. The panel button "Preparar tudo" (Vendas screen, Conexão tab) runs exactly the same thing; mention it once.

## Run

1. Project root = the folder that has `.tune-up/`. Panel port = `porta` in `.tune-up/painel.json`, else 8787.
2. Run the setup in the background (it can take many minutes the first time) and follow its output:

   ```
   python3 -B "${CLAUDE_PLUGIN_ROOT}/servico/preparo.py" rodar --projeto "<project root>" --painel http://127.0.0.1:<panel port>
   ```

   On Windows use `python` instead of `python3`. Never add other options.
3. Each step prints its title, then `feito`, `falhou` or `precisa_do_dono` with a plain message. Relay each one in a short sentence (e.g. "Passo 2 de 5: ligando o programa que roda o WhatsApp... feito.").
4. Exit code 0 = everything is ready: tell the owner to open the panel, Vendas > Conexão, and read the QR code. Exit code 3 = a setup is already running for this project: say so and stop. Exit code 2 = the project folder was refused: relay the message.

## When the owner must act (`precisa_do_dono`)

- Show the plain message and the printed `comando:` line exactly, in a code block, and ask the owner to paste it into their own terminal.
- Then WAIT for the owner to say it is done, and run the same command of step 2 again (it resumes from the first step that is missing).
- NEVER run that command yourself. NEVER run `sudo`. NEVER pipe a download into a shell (`curl ... | sh`, `iwr ... | iex`). NEVER install anything the setup did not print.

## When a step fails (`falhou`)

Relay the plain message, offer to run step 2 again once, and stop if it fails the same way. Do not read or print the setup log, the `.env` or anything in the data folder: they may hold keys.
