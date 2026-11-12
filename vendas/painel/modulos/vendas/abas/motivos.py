"""Frases em português simples para os códigos de motivo do serviço (a tela nunca mostra o código cru)."""
MOTIVOS = {
    "optout_pede_confirmacao": "Este contato pediu para sair. Para escrever mesmo assim, use o botão \"Liberar uma "
                               "mensagem\" e envie de novo.",
    "optout": "Este contato pediu para sair; nada é enviado a ele.",
    "teto_minuto": "Muitas mensagens no último minuto (limite de 8). Espere um pouco e tente de novo.",
    "teto_hora": "Muitas mensagens na última hora. Espere um pouco e tente de novo.",
    "pausa_humana": "A conversa está com você; a IA não escreve nela.",
    "fora_da_janela": "Fora do horário permitido para esse tipo de envio.",
    "numero_invalido": "Este número não está no WhatsApp; a mensagem não saiu.",
    "fuso_invalido": "O fuso do projeto está inválido; corrija a configuração.",
    "nao_reenviavel": "Este envio não pode mais ser reenviado.",
    "nao_incerto": "Este envio já foi decidido.",
    "chave_ocupada": "Essa mensagem já foi registrada antes (clique repetido ignorado).",
    "descartado_pelo_dono": "Marcada por você como não enviada.",
    "pendente_na_subida": "O serviço reiniciou no meio do envio: não sei se saiu.",
    "sem_numero_do_dono": "O número do dono não está configurado.",
    "pedir_humano": "A IA pediu para você assumir esta conversa.",
    "erro_interno": "A IA falhou nesta conversa e foi desligada nela.",
    "rodadas": "A IA não chegou a uma resposta (voltou a chamar ferramentas) e foi desligada nesta conversa.",
    "anti_loop": "A IA repetiu a mesma resposta 3 vezes e foi desligada nesta conversa.",
    "campanha_parada": "A campanha deste envio está pausada. Retome-a na aba Disparos para reenviar.",
    "contato_fora_da_campanha": "Este contato já não espera este envio na campanha (respondeu ou saiu dela).",
    "sem_optout": "Essa confirmação só vai para quem pediu para sair.",
    "nao_e_o_dono": "O teste de áudio só vai para o número do dono.",
    "teto_teste_audio_dia": "Acabou o limite de testes de áudio de hoje.",
    "teto_audio_dia": "Acabou o limite de áudios da IA de hoje.",
    "teto_audio_contato_dia": "Acabou o limite de áudios da IA para este contato hoje; a resposta foi em texto.",
    "audio_incerto": "O áudio da IA pode não ter chegado; confira no celular e responda você.",
    "rascunho_links_nao_sairam": "O áudio saiu, mas o texto com os links não. Aprove de novo para mandar só os links.",
    "teto_contatos_novos_dia": "Aquecimento: acabou o limite de contatos novos de hoje para este número.",
    "teto_diario": "A IA atingiu o teto de gasto do dia; responda você.",
    "sem_chave": "A IA está sem chave da OpenAI; configure na aba IA.",
    "sem_modelo": "A IA está sem modelo escolhido; configure na aba IA.",
    "sem_oferta": "A IA está sem oferta cadastrada; configure na aba IA.",
    "preco_desconhecido": "O preço do modelo da IA não está cadastrado; informe na aba IA.",
    "resposta_invalida": "A IA devolveu uma resposta inválida; responda você.",
    "resposta_cortada": "A resposta da IA veio cortada no meio e não foi enviada; responda você.",
    "sem_texto": "A IA não escreveu nada; responda você.",
    "reescrita_falhou": "A IA escreveu um comando em vez de texto e a correção falhou; nada saiu, responda você.",
    "ferramenta_como_texto": "A IA escreveu um comando em vez de texto; nada saiu, responda você.",
    "segredo": "A resposta da IA trazia algo parecido com uma chave e foi barrada.",
    "link_suspeito": "A resposta da IA trazia um link fora da lista e foi barrada.",
    "vazio": "A resposta da IA ficou vazia depois dos filtros e não saiu.",
    "rascunho_em_aprovacao": "Este rascunho já está sendo aprovado.",
    "gatilho_ja_respondido": "Essa mensagem do lead já foi respondida.",
    "gatilho_ja_tem_rascunho": "Essa mensagem do lead já tem um rascunho.",
    "envio_negado": "A resposta da IA não saiu; responda você.",
    "envio_parcial": "A resposta da IA saiu só em parte; complete você.",
    "sem_conector": "O WhatsApp não está conectado; a IA não respondeu.",
    "injecao_suspeita": "A mensagem do lead parece tentar mandar na IA; responda você.",
    "audio_longo": "O áudio do lead passa de 5 minutos ou 16 MB; a IA não ouviu. Responda você.",
    "audio_formato": "O formato do áudio do lead não é aceito pela transcrição; responda você.",
    "transcricao_falhou": "A transcrição do áudio do lead falhou; a IA não respondeu. Ouça e responda você.",
    "midia_indisponivel": "O áudio ou a imagem do lead não baixou a tempo; a IA não respondeu. Responda você.",
    "midia_desligada": "A IA não entende áudios ou imagens (desligado na aba IA); responda você.",
    "imagens_demais": "O lead mandou imagens demais de uma vez; a IA viu só as últimas. Confira as outras.",
    "imagem_grande": "A imagem do lead passa de 8 MB; a IA não viu. Responda você.",
    "sinal_de_saida": "O lead falou em sair ou parar num áudio ou legenda; confira a conversa.",
    "modelo_sem_visao": "O modelo da IA não aceita imagens; nada saiu. Troque o modelo ou responda você.",
    "documento_recebido": "O lead mandou um documento; a IA não lê documentos. Responda você.",
}


def motivo_pt(motivo):
    motivo = motivo or ""
    if motivo in MOTIVOS:
        return MOTIVOS[motivo]
    if motivo.startswith("incerto") or motivo.startswith("erro_inesperado") or motivo == "sem_id_externo":
        return "O WhatsApp não confirmou se a mensagem saiu."
    if motivo.startswith("nao_enviado"):
        return "O WhatsApp recusou a mensagem; ela não saiu."
    return "O envio não foi permitido." if motivo else ""
