# Rhythm

Read by the video skill in Strategy (pick the arc for `arquetipo`) and in the Script step (what each scene of the kit says, words, times).
pt-BR lines are molds from invented businesses: every fact in a reel comes from the briefing or the brand kit.

## Allowed scene patterns
The QA check `cenas` passes only when: D10 has 4 or 5 scenes, D15 has 5 or 6; scene 1 ≤ 2.0 s; the last ≥ 2.5 s; every scene ≥ 1.5 s; scenes are contiguous from 0; the sum is D ± 0.05. `folha_limpa` adds: every cut sits off the 0.25 s grid (a frame sampled every 0.5 s never shows a transition). The kit uses the first, the second (a reel with a style scene) and the fourth row.

| D | lengths (`--tempos`) | scene starts | snapshot `--at` (0 + middles) | cuts | `tr<N>` `data-start` | `deco1` cut % |
|---|---|---|---|---|---|---|
| 10 | `1.875,2.5,2.5,3.125` | 0, 1.875, 4.375, 6.875 | `0,0.9375,3.125,5.625,8.4375` | 1.875, 4.375, 6.875 | 1.655, 4.155, 6.655 | 18.8, 43.8, 68.8 |
| 10 | `1.625,2.75,2.5,3.125` | 0, 1.625, 4.375, 6.875 | `0,0.8125,3,5.625,8.4375` | 1.625, 4.375, 6.875 | 1.405, 4.155, 6.655 | 16.3, 43.8, 68.8 |
| 10 | `1.875,2,2,1.5,2.625` | 0, 1.875, 3.875, 5.875, 7.375 | `0,0.9375,2.875,4.875,6.625,8.6875` | 1.875, 3.875, 5.875, 7.375 | 1.655, 3.655, 5.655, 7.155 | 18.8, 38.8, 58.8, 73.8 |
| 15 | `1.875,3,3,3,4.125` | 0, 1.875, 4.875, 7.875, 10.875 | `0,0.9375,3.375,6.375,9.375,12.9375` | 1.875, 4.875, 7.875, 10.875 | 1.655, 4.655, 7.655, 10.655 | 12.5, 32.5, 52.5, 72.5 |
| 15 | `1.875,2.5,2.5,2.5,2.5,3.125` | 0, 1.875, 4.375, 6.875, 9.375, 11.875 | `0,0.9375,3.125,5.625,8.125,10.625,13.4375` | 1.875, 4.375, 6.875, 9.375, 11.875 | 1.655, 4.155, 6.655, 9.155, 11.655 | 12.5, 29.2, 45.8, 62.5, 79.2 |

The 5-scene row at D10 and the 6-scene row at D15 are for a hand-made reel with a list or 3 steps; the kit's 15 s reel has its own list scene.

## Reading
| scene length (s) | 1.5 | 2 | 2.5 | 3 | 3.5 | 4 |
|---|---|---|---|---|---|---|
| max words, all text layers of the scene added (`max(6, floor(3 x length))`; 1.875 s gives 6, 2.75 s gives 8, 3.125 s gives 9, 4.125 s gives 12) | 6 | 6 | 7 | 9 | 10 | 12 |

- Count every text clip of the scene: `titulo` + `destaque` + `apoio`/`selo`/`item*`/`contato` (the brand name `marca` is not counted).
- In scene 1 the visual action is a photo or a shape, so the headline and the accent word share the 6 words. "Sai às 6h10." + "Acaba às 7h." = 6.
- A title of 3-5 words needs at least 1.3 s on screen before the cut.
- The title is whole at the cut; the 2nd line of a scene rises in at 0.5-0.7 s, early enough to stay on screen 0.5 s + 0.3 s a word (the check flags `line_unread`).
- The last scene shows its call, contact and brand from its first frame to the end (the HyperFrames check flags `line_unread` under 2 s).

## Curve
- Fast hook (1.5-2 s), a slightly slower middle (2.5-3 s), a firm CTA (2.5-4 s). Nothing moves in a metronome: lengths are not all equal.
- Something moves every 0.5 s: the hero drifts and its loops run the whole video, words wave, a line draws itself, the ring pulses; 0.75 s almost still anywhere but the last 1 s fails `movimento`, 1 s frozen fails `freezedetect`. No clip exits: the transition hides the cut.
- One dominant movement per scene; the hero's change belongs to the offer scene alone.
- `l-*` changes at every cut; the logo and the brand name appear from scene 2 on, in the same corner.

## On-ramp and payoff
- Scene 2 continues the sentence of scene 1. If scene 1 asks "Dá para cortar antes das 9h?", scene 2 starts the answer, never the brand story.
- The second-to-last scene pays the promise with the fact (number, hour, price, the customer's words) while the hero changes with it (heroi.md: before and after). A price or an hour is there, whole, from the cut: never counted up.
- The last scene asks for one action: verb + a gain not said yet in `sN_titulo` (never the payoff's offer again), the briefing's condition and deadline, the channel icon + `sN_contato`, the brand name in `sN_marca`.

## Arcs by objective
Scene jobs in order: D10 has 4 scenes (skip the "D15 only" column), D15 has 5. Molds come from invented businesses.

| arc (objectives) | 1 hook | 2 on-ramp | 3 (D15 only) | payoff | CTA |
|---|---|---|---|---|---|
| **Proof first** (vender, ensinar) | the result: "Seco em 40 min" | how: "Toalha e ar frio" | the detail: "Um pet por vez" | proof: "1.240 banhos este ano" | "Agende o banho de sábado" |
| **PAS** (receber mensagens, encher a agenda) | the pain: "Chiado ao frear?" | consequence: "Pastilha no fim risca o disco" | cost of waiting, only if written | the solution: "Revisão de freio em 1 hora" | "Mande a placa e receba o horário" |
| **Before, bridge, after** (vender) | before: "Travava no telefone em inglês" | after: "Hoje fecha pedido com fornecedor" | the bridge: "Aula de conversa, 4 por turma" | proof: "Ana, aluna desde março" | "Faça a aula experimental" |
| **Objection** (encher a agenda, vender) | the doubt: "Atende sábado?" | the answer: "Sim, das 8h às 13h" | the visit: "Avaliação e plano no mesmo dia" | proof: "Nota 4,9 em 310 avaliações" | "Garanta seu sábado" |
| **Novelty** (lançar novidade) | the new thing big: "Novo: provador até 21h" | what changes for the customer: "Saiu do trabalho, ainda dá" | since when: "Às sextas, desde maio" | the photo or the first proof | "Passe na sexta e prove" |
| **Situation** (short briefing, any objective) | the reader's situation + its figure: "Carro parado na porta?" | the pain, 3-5 words; the same figure, closer | a second beat, never the business description | the offer as giant number or sticker; the figure transformed | verb + where + a new gain: "Mande a placa e escolha o dia" |

**Demo in 3 steps** (receber mensagens, ensinar) uses the 5- and 6-scene patterns: the result ("DAS pago sem abrir o portal") / D15 only, the map ("3 passos, 5 minutos") / "1. Mande a nota no WhatsApp" / "2. Receba a guia no dia" / "3. Pague pelo app do banco" (payoff) / "Mande OI e comece".

- Renumber the scenes 1..N in `roteiro.md` (ids `s1..sN`).
- The payoff brings a fact the hook did not show: if the hook is the hour, the payoff is the proof or the offer, never the hour again.
- Short briefing: **Situation** with the fewest scenes the QA accepts (4 at 10 s, 5 at 15 s); a scene may be a device and up to 3 words.
