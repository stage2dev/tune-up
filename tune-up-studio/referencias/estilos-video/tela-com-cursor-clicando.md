# Video style: tela com cursor clicando

Read by the video skill only when this is the piece's style (`"estilo": "tela-com-cursor-clicando"` in `peca.json`); no other style file is read.
Distilled from the interface films of the collection credited in NOTICE (a cursor that causes every change with a real click, a ring spreading from the click point, the button answering, the cursor aimed at where the target is). Rebuilt for the studio engine (one hero, no library, no network, no 3D, no sound), rendered and looked at frame by frame in round 7. The pt-BR lines are molds of an invented booking app for a sports court: never reuse one (QA `molde`).

## Use it when
The product is a screen (an app, a site, a system) or the wanted action is a click the reader can copy (book online, buy on the site, start a free trial). The reader sees the one tap that solves it.

## Slots of scene 2 (`tela`, 8 words; 9 at 15 s)
| slot | limit | what goes there |
|---|---|---|
| `tela.titulo` | 28 characters | what the click does, 2 to 4 words ("Reserve em um toque") |
| `tela.botao` | 18 characters | the button as the product or the site writes it ("Reservar quadra"); 1 or 2 words |
| `tela.feito` | 18 characters | what the button shows after the click, a fact ("Quadra reservada"); 1 or 2 words |

## Storyboard, 10 s
Cuts at 1.625, 4.375 and 6.875 s. Times inside scene 2 count from its cut.
| time | scene | what the eye sees |
|---|---|---|
| 0-1.625 | 1 `gancho` | the hook at the top, a marker drawing under its key words at 0.4 s; the hero wide, pushed in |
| 1.625-4.375 | 2 `tela` | the title and a light card (two dots, two gray lines, the button) whole at the cut; the cursor travels from the lower right and reaches the button at 0.9 s; at 1.05 s it presses, a ring spreads from the point, the button takes the accent color and shows the done text, which pulses; the cursor leaves by 1.8 s; a second pulse at 1.95 s; the hero small below |
| 4.375-6.875 | 3 `oferta` | the offer's name on a tag, the price or offer word giant on the accent band, the proof; the hero changes (`h_antes` fades, `h_depois` pops, `h_traco` draws) |
| 6.875-10 | 4 `final` | the call big, the condition on its tag, the contact beside the channel icon; a cursor travels to the contact and presses it at 1.3 s; logo and brand name; the hero 45% wide or more |

## 15 s
Cuts at 1.875, 4.875, 7.875 and 10.875 s. Scene 2 is the same, 3 s long. Then scene 3 is `rampa` (the hero in close-up over one more fact: `rampa.titulo` 36 characters + `rampa.apoio` 40, 9 words), then `oferta` (9 words) and `final` (12 words).

## Where the method enters
The hook is scene 1 (the problem the screen solves). The card is a drawing of one action, not a tour: one button, no menu, no field the briefing does not name. The offer scene carries the price or the trial; `final.canal` is `site` (or `instagram`) and the end card's cursor presses the contact again.

## Never
- A copy of a real product's interface, logo or name other than the brand's own.
- Two clicks, a form being typed, a loading bar: one click, one answer.
- A done text that promises a result ("Lucro garantido"); it states what happened ("Pedido enviado").
