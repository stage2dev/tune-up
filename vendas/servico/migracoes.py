"""Migrações do banco (PRAGMA user_version): a posição na lista é a versão. Nunca edite uma que já saiu;
acrescente no fim."""

MIGRACOES = [
    # 1: esquema inicial
    [
        """CREATE TABLE contatos (
            id INTEGER PRIMARY KEY,
            telefone TEXT NOT NULL UNIQUE,
            telefone_alt TEXT UNIQUE,
            nome TEXT,
            origem TEXT,
            base_legal TEXT,
            optout_em TEXT,
            criado_em TEXT NOT NULL)""",
        """CREATE TABLE conversas (
            id INTEGER PRIMARY KEY,
            contato_id INTEGER NOT NULL UNIQUE REFERENCES contatos(id),
            modo TEXT NOT NULL DEFAULT 'ia' CHECK (modo IN ('ia', 'humano')),
            pausada_ate TEXT,
            estado TEXT,
            precisa_de_voce INTEGER NOT NULL DEFAULT 0 CHECK (precisa_de_voce IN (0, 1)),
            criado_em TEXT NOT NULL)""",
        """CREATE TABLE mensagens (
            id INTEGER PRIMARY KEY,
            conversa_id INTEGER NOT NULL REFERENCES conversas(id),
            id_externo TEXT UNIQUE,
            direcao TEXT NOT NULL CHECK (direcao IN ('entrada', 'saida')),
            tipo TEXT NOT NULL DEFAULT 'texto',
            texto TEXT,
            criado_em TEXT NOT NULL)""",
        """CREATE TABLE envios (
            id INTEGER PRIMARY KEY,
            chave_dedupe TEXT NOT NULL,
            contato_id INTEGER REFERENCES contatos(id),
            estado TEXT NOT NULL
                CHECK (estado IN ('pendente', 'enviado', 'falhou', 'negado', 'incerto')),
            origem TEXT NOT NULL,
            motivo TEXT,
            id_externo TEXT,
            criado_em TEXT NOT NULL)""",
        "CREATE UNIQUE INDEX envios_chave_dedupe ON envios(chave_dedupe) WHERE estado <> 'negado'",
        """CREATE TABLE campanhas (
            id INTEGER PRIMARY KEY,
            nome TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'rascunho',
            criado_em TEXT NOT NULL)""",
        """CREATE TABLE campanha_contatos (
            campanha_id INTEGER NOT NULL REFERENCES campanhas(id),
            contato_id INTEGER NOT NULL REFERENCES contatos(id),
            passo INTEGER NOT NULL DEFAULT 0,
            estado TEXT NOT NULL DEFAULT 'pendente',
            PRIMARY KEY (campanha_id, contato_id))""",
        """CREATE TABLE eventos (
            id INTEGER PRIMARY KEY,
            tipo TEXT NOT NULL,
            dados TEXT,
            criado_em TEXT NOT NULL)""",
        "CREATE TABLE config (chave TEXT PRIMARY KEY, valor TEXT)",
        "CREATE TABLE batimento (id INTEGER PRIMARY KEY CHECK (id = 1), pid INTEGER, em TEXT NOT NULL)",
    ],
    # 2: o portão guarda destino e conteúdo do envio (para o dono reenviar a MESMA linha) e conta por tempo
    [
        "ALTER TABLE envios ADD COLUMN telefone TEXT",
        "ALTER TABLE envios ADD COLUMN tipo TEXT",
        "ALTER TABLE envios ADD COLUMN conteudo TEXT",
        "CREATE INDEX envios_criado_em ON envios(criado_em)",
    ],
    # 3: os tetos contam a ÚLTIMA tentativa (reserva ou reenvio), não a criação da linha
    [
        "ALTER TABLE envios ADD COLUMN tentado_em TEXT",
        "UPDATE envios SET tentado_em = criado_em WHERE tentado_em IS NULL",
        "CREATE INDEX envios_tentado_em ON envios(tentado_em)",
    ],
    # 4: uma linha por TENTATIVA (reserva ou reenvio): os tetos contam aqui, o reenvio não apaga a anterior
    [
        """CREATE TABLE tentativas (
            id INTEGER PRIMARY KEY,
            envio_id INTEGER NOT NULL REFERENCES envios(id),
            origem TEXT NOT NULL,
            estado TEXT NOT NULL CHECK (estado IN ('pendente', 'enviado', 'falhou', 'incerto')),
            em TEXT NOT NULL)""",
        "CREATE INDEX tentativas_em ON tentativas(em)",
        "CREATE INDEX tentativas_envio ON tentativas(envio_id)",
        "INSERT INTO tentativas (envio_id, origem, estado, em) "
        "SELECT id, origem, estado, COALESCE(tentado_em, criado_em) FROM envios WHERE estado <> 'negado'",
    ],
    # 5: recebimento: mensagem de saída ligada ao envio que ela ecoa (um eco por envio) e mapa @lid -> telefone
    [
        "ALTER TABLE mensagens ADD COLUMN envio_id INTEGER REFERENCES envios(id)",
        "CREATE UNIQUE INDEX mensagens_envio ON mensagens(envio_id) WHERE envio_id IS NOT NULL",
        "CREATE TABLE lids (lid TEXT PRIMARY KEY, telefone TEXT NOT NULL, criado_em TEXT NOT NULL)",
    ],
    # 6: mensagem de webhook sem segredo fica marcada (0): a IA não a lê nem responde a ela
    [
        "ALTER TABLE mensagens ADD COLUMN confiavel INTEGER NOT NULL DEFAULT 1 CHECK (confiavel IN (0, 1))",
    ],
    # 7: por que a IA ficou desligada nesta conversa (pedir_humano, erro, anti-loop); some ao devolver para a IA
    [
        "ALTER TABLE conversas ADD COLUMN motivo_humano TEXT",
    ],
    # 8: modo da IA por conversa (NULL = o padrão do projeto) e rascunhos que o dono aprova, edita ou descarta
    [
        "ALTER TABLE conversas ADD COLUMN modo_ia TEXT CHECK (modo_ia IN ('rascunho', 'automatico'))",
        """CREATE TABLE rascunhos (
            id INTEGER PRIMARY KEY,
            conversa_id INTEGER NOT NULL REFERENCES conversas(id),
            mensagem_id INTEGER NOT NULL REFERENCES mensagens(id),
            texto TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'pendente'
                CHECK (estado IN ('pendente', 'aprovado', 'descartado', 'substituido', 'expirado', 'negado')),
            criado_em TEXT NOT NULL,
            decidido_em TEXT)""",
        "CREATE UNIQUE INDEX rascunhos_gatilho ON rascunhos(conversa_id, mensagem_id)",
        "CREATE UNIQUE INDEX rascunhos_pendente ON rascunhos(conversa_id) WHERE estado = 'pendente'",
    ],
    # 9: 'aprovando' = a aprovação travou o rascunho e está no portão (descartar e rascunho novo esperam por ela);
    # o SQLite não muda CHECK, então a tabela é refeita com os mesmos dados
    [
        """CREATE TABLE rascunhos_9 (
            id INTEGER PRIMARY KEY,
            conversa_id INTEGER NOT NULL REFERENCES conversas(id),
            mensagem_id INTEGER NOT NULL REFERENCES mensagens(id),
            texto TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'pendente' CHECK (estado IN ('pendente', 'aprovando', 'aprovado',
                'descartado', 'substituido', 'expirado', 'negado')),
            criado_em TEXT NOT NULL,
            decidido_em TEXT)""",
        "INSERT INTO rascunhos_9 (id, conversa_id, mensagem_id, texto, estado, criado_em, decidido_em) "
        "SELECT id, conversa_id, mensagem_id, texto, estado, criado_em, decidido_em FROM rascunhos",
        "DROP TABLE rascunhos",
        "ALTER TABLE rascunhos_9 RENAME TO rascunhos",
        "CREATE UNIQUE INDEX rascunhos_gatilho ON rascunhos(conversa_id, mensagem_id)",
        "CREATE UNIQUE INDEX rascunhos_pendente ON rascunhos(conversa_id) WHERE estado IN ('pendente', 'aprovando')",
    ],
    # 10: campanha = modelo + contatos; o agendador guarda o motivo, quando tentar de novo e o envio de cada contato
    [
        "ALTER TABLE campanhas ADD COLUMN modelo TEXT",
        "ALTER TABLE campanhas ADD COLUMN motivo TEXT",
        "ALTER TABLE campanhas ADD COLUMN falhas_seguidas INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE campanha_contatos ADD COLUMN motivo TEXT",
        "ALTER TABLE campanha_contatos ADD COLUMN tentar_depois TEXT",
        "ALTER TABLE campanha_contatos ADD COLUMN envio_id INTEGER REFERENCES envios(id)",
        "ALTER TABLE campanha_contatos ADD COLUMN ordem INTEGER NOT NULL DEFAULT 0",
        "CREATE INDEX campanha_contatos_fila ON campanha_contatos(estado, tentar_depois)",
        "ALTER TABLE envios ADD COLUMN instancia TEXT",   # aquecimento e "contato novo" valem por instância
    ],
    # 11: criar campanha pela tela é idempotente (o mesmo id_cliente nunca cria duas)
    [
        "ALTER TABLE campanhas ADD COLUMN id_cliente TEXT",
        "CREATE UNIQUE INDEX campanhas_id_cliente ON campanhas(id_cliente) WHERE id_cliente IS NOT NULL",
    ],
    # 12: candidatos do buscador de leads (só dado de empresa; a revisão do dono vem depois)
    [
        """CREATE TABLE candidatos (
            id INTEGER PRIMARY KEY,
            nome TEXT NOT NULL,
            site TEXT,
            telefone TEXT,
            url_da_fonte TEXT,
            nicho TEXT,
            cidade TEXT,
            estado TEXT NOT NULL DEFAULT 'novo',
            criado_em TEXT NOT NULL)""",
        "CREATE UNIQUE INDEX candidatos_telefone ON candidatos(telefone) WHERE telefone IS NOT NULL",
        "CREATE UNIQUE INDEX candidatos_nome ON candidatos(nome, ifnull(cidade, ''), ifnull(nicho, ''))",
    ],
    # 13: revisão do dono: data da decisão, contato criado/mesclado na aprovação e site normalizado (anti re-sugestão)
    [
        "ALTER TABLE candidatos ADD COLUMN decidido_em TEXT",
        "ALTER TABLE candidatos ADD COLUMN contato_id INTEGER",
        "ALTER TABLE candidatos ADD COLUMN site_host TEXT",
        "CREATE INDEX candidatos_site_host ON candidatos(site_host) WHERE site_host IS NOT NULL",
    ],
    # 14: Google Places (termos do Google): só o place_id (+ nicho e cidade da busca) é guardado; nada de nome, telefone
    # ou endereço. places_uso conta as buscas do dia (teto diário aplicado aqui, no banco).
    [
        """CREATE TABLE places_guardados (
            place_id TEXT PRIMARY KEY,
            nicho TEXT NOT NULL,
            cidade TEXT NOT NULL,
            criado_em TEXT NOT NULL)""",
        "CREATE TABLE places_uso (dia TEXT PRIMARY KEY, n INTEGER NOT NULL)",
    ],
    # 15: voz (ElevenLabs): caracteres reservados por dia (teto antes de chamar) e consentimento do dono da voz clonada
    [
        "CREATE TABLE voz_uso (dia TEXT PRIMARY KEY, caracteres INTEGER NOT NULL)",
        """CREATE TABLE voz_consentimentos (
            id INTEGER PRIMARY KEY,
            voz_id TEXT NOT NULL,
            nome TEXT NOT NULL,
            data TEXT NOT NULL,
            texto TEXT NOT NULL,
            criado_em TEXT NOT NULL)""",
    ],
    # 16: rascunho que a IA quer mandar como áudio (responder_em_audio): o áudio só é gerado na aprovação
    ["ALTER TABLE rascunhos ADD COLUMN como_audio INTEGER NOT NULL DEFAULT 0"],
    # 17: nome do perfil do WhatsApp (o nome do CSV/dono em `nome` sempre vence) e até qual mensagem o dono já leu
    [
        "ALTER TABLE contatos ADD COLUMN nome_whatsapp TEXT",
        "ALTER TABLE conversas ADD COLUMN lida_ate INTEGER",
        "CREATE INDEX mensagens_conversa ON mensagens(conversa_id, id)",
    ],
    # 18: mídia recebida (áudio, imagem, documento). `chave` = a chave da mensagem na Evolution (id, remoteJid,
    # fromMe), `arquivo` = "<conversa>/<nome aleatório>" sob <pasta de dados>/midia; nunca um caminho vindo de pedido.
    [
        """CREATE TABLE midias (
            id INTEGER PRIMARY KEY,
            mensagem_id INTEGER NOT NULL UNIQUE REFERENCES mensagens(id),
            tipo TEXT NOT NULL CHECK (tipo IN ('audio', 'imagem', 'documento')),
            chave TEXT,
            mimetype TEXT,
            bytes INTEGER,
            sha256 TEXT,
            nome_arquivo TEXT,
            arquivo TEXT,
            duracao_s REAL,
            estado TEXT NOT NULL DEFAULT 'pendente'
                CHECK (estado IN ('pendente', 'pronta', 'falhou', 'expirada')),
            motivo TEXT,
            criado_em TEXT NOT NULL,
            baixada_em TEXT)""",
        "CREATE INDEX midias_estado ON midias(estado, baixada_em)",
    ],
]
