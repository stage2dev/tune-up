# Video style: conversa de WhatsApp

Read by the video skill only when this is the piece's style (`"estilo": "conversa-de-whatsapp"` in `peca.json`); no other style file is read.
Distilled from the prompts of the collection credited in NOTICE that open on a typed request (the customer's own words on screen, a real typing rhythm, the answer arriving as the next beat). Rebuilt for the studio engine (one hero, no library, no network, no 3D, no sound), rendered and looked at frame by frame in round 7. The pt-BR lines are molds of an invented flower shop: never reuse one (QA `molde`).

## Use it when
The wanted action is a message (`receber mensagens`, `encher a agenda`, orders by chat) or the briefing answers a question customers always ask (price, time, delivery). The reader sees how easy the first message is.

## Slots of scene 2 (`conversa`, 8 words; 9 at 15 s)
| slot | limit | what goes there |
|---|---|---|
| `conversa.pergunta` | 28 characters | what a customer types, in the customer's words, with the question mark ("Entrega buquê hoje?"); 2 to 4 words |
| `conversa.respostas` | 1 or 2 answers, 26 characters each | the business's reply, each one a fact of the briefing ("Entrega até as 18h", "Sem taxa no centro"); 2 or 3 words each |

## Storyboard, 10 s
Cuts at 1.625, 4.375 and 6.875 s. Times inside scene 2 count from its cut.
| time | scene | what the eye sees |
|---|---|---|
| 0-1.625 | 1 `gancho` | the hook at the top, a marker drawing under its key words at 0.4 s; the hero wide, pushed in |
| 1.625-4.375 | 2 `conversa` | the brand's logo and name head the chat; the question big in a light bubble, whole at the cut; three typing dots bounce on the right; answer 1 pops from its corner at 0.7 s; the dots come back lower; answer 2 pops at 1.4 s and pulses at 2.05 s; the hero small on its stage below |
| 4.375-6.875 | 3 `oferta` | the offer's name on a tag, the price or offer word giant on the accent band, the proof; the hero changes (`h_antes` fades, `h_depois` pops, `h_traco` draws) |
| 6.875-10 | 4 `final` | the call big, the condition on its tag, the contact beside the channel icon; a cursor travels to the contact and presses it at 1.3 s; logo and brand name; the hero 45% wide or more |

## 15 s
Cuts at 1.875, 4.875, 7.875 and 10.875 s. Scene 2 is the same, 3 s long. Then scene 3 is `rampa` (the hero in close-up over one more fact: `rampa.titulo` 36 characters + `rampa.apoio` 40, 9 words), then `oferta` (9 words) and `final` (12 words).

## Where the method enters
The hook is still scene 1 (the reader's situation); the chat shows the way out, it is not the hook. The price waits for scene 3: an answer never carries it. `final.canal` is `whatsapp` and `final.contato` the number or `pelo WhatsApp` exactly as the briefing writes it.

## Never
- An answer that promises what the briefing does not say (a deadline, a discount, "sempre").
- A long, polite exchange ("Olá, tudo bem?"): the question is the first thing typed.
- A fake screen of the real app (its green, its ticks, its header): the chat uses the brand's colors only.
- A customer name, a phone number or a photo in the chat.
