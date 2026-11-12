# The hero (the one drawing of the piece)

Read by the post and video skills before they draw `heroi.svg`: the kit lays out everything else, so this drawing is where the piece becomes this business's own.
Every example below was drawn, assembled by the kit, rendered and looked at (round 6: a garage, a pet shop, a bakery, a software product). They show the construction; never copy their shapes.

## What the hero is
One object in one moment, taken from the briefing: what the reader has in hand, sits in, eats or looks at when the offer matters (the car loaded for the trip, the dog in the tub, the basket by the oven, the screen of the product). Not the sector's symbol: a wrench, a tooth, a scissor, a paw, a cup alone are pictograms and the kit refuses a drawing of fewer than 12 shapes.
- It carries **one detail only this briefing has**: the luggage on the roof (a holiday check-up), the mud that the bath removes, the loaves of the first batch, the chart the product shows.
- It has **a before and an after**: what the offer changes. The reel plays the change in the offer scene; the post shows the after.
- When `fotos.py` printed a main photo of the product or the place, the photo is the hero: write `"heroi": "foto"` in `peca.json` and draw nothing. A photo has no before and after: the offer scene then lives on the price.

## The box
`<svg viewBox="0 0 1000 1000">`, nothing else in the root tag. The ground is the line **y = 900**: the object stands on it (wheels, feet, base). The drawing fills the box: 800 or more wide, or 700 or more tall, centered on x = 500. Write the y of its highest point in `peca.json` as `"heroi_topo"` (the kit sizes the hero by it). Coordinates are absolute numbers; no `style`, no `fill="#..."`, no text, no image, no `use`.

## Colors, by class only
| fill | stroke (round caps, set `stroke-width`) | brand color |
|---|---|---|
| `p` | `lp` | primary |
| `a` | `la` | accent |
| `t` | `lt` | text (the darkest: shadows, tires, outlines) |
| `s` | `ls` | surface (light planes: glass, cloth, foam shade) |
| `b` | `lb` | bg (the lightest: shine, paper, foam) |

The kit always puts the hero on a light stage (`bg`), so the big masses are `p`, `a` or `t`; `b` and `s` are for what sits inside a mass.

## Build it in 5 layers (back to front)
1. **Masses**: the silhouette in 2 or 3 big shapes (`path` with `Q` curves and rounded `rect`), in one main color. Squint: the object reads from the masses alone.
2. **Second tone**: the lower third or the far side again in `t` (a skirt, a bumper, the base of the tub, the bottom of the basket). Two tones are the volume; no gradient, no blur.
3. **Light planes**: what is glass, cloth, paper or foam in `s` and `b`; one small shine (`ls` or `lb` stroke) on the main mass.
4. **Lines**: 4 to 10 strokes in `lt` (door line, weave, whiskers, handles), `stroke-width` 6 to 14; a main contour (a handle, a steam line, a tick) 16 to 26. The widths are drawn as written: vary them.
5. **The briefing's detail and the change**: the parts listed below.

## Parts the kit animates (ids)
Everything is optional except `h_corpo` and, for a reel, one `h_depois*` or `h_traco*`.

| id | what it is | how to draw it | the reel does | the post shows |
|---|---|---|---|---|
| `h_corpo` | `<g>` with the object itself | layers 1 to 4 | reframes it at every cut, drifts it | yes |
| `h_gira1..4` | a part that turns (wheel, fan, dial) | around 0,0 inside `<g transform="translate(x y)">` | turns the whole video | yes |
| `h_balanca1..4` | parts that float (bubbles, steam, a tag) | in place | bobs 34 px | yes |
| `h_antes1..4` | the problem state (mud, crumbs, the messy sheet) | in place, over or behind the body | fades out in the offer scene | hidden |
| `h_depois1..6` | what the offer adds (ticks, loaves, a bow, bars, sparkles) | around 0,0 inside `<g transform="translate(x y)">` | pops in one by one, with overshoot | yes |
| `h_traco1..4` | a line that draws itself (steam, a trend line, a tick) | one `path` with `pathLength="1"` | draws it in the offer scene | yes |

An `h_depois` part drawn behind the body goes before `h_corpo` in the file (the loaves behind the basket's rim). A badge gets its own shadow: the same circle in `t`, 6 px down and right, under it.

## Worked examples (in `${CLAUDE_PLUGIN_ROOT}/kit/herois/`; Read the one closest in construction, one only)
| file | object and moment | briefing detail | before -> after | shapes |
|---|---|---|---|---|
| `carro-com-bagagem.svg` | a hatchback in profile on the road, two-tone body, glass in two planes | two suitcases on the roof rack (a holiday check-up) | nothing -> three "checked" badges pop on wheels and glass; the wheels turn | 42 |
| `cao-na-banheira.svg` | a dog's head and paws over the rim of a footed tub, foam on the rim | the bath itself, bubbles floating | mud spots and stink lines -> a bow tie and sparkles | 47 |
| `cesta-de-paes.svg` | a wicker basket with a checkered cloth, handle behind | the first batch | crumbs -> three loaves drop in behind the rim, steam draws itself | 22 |
| `tela-de-app.svg` | a monitor on its foot, the product's window in it | the one number the product shows, as a chart | a tilted spreadsheet behind -> bars rise, a trend line draws, a badge pops | 22 |

What they share: the object fills the box and is cut by nothing; two tones on the main mass; a detail a competitor's piece would not have; an after that is visible from across the room.

## Check it before assembling
- Does it read at a third of the size? Is the briefing's detail one of the three biggest things in it?
- Is every color a class? Does it stand on y = 900? Is `heroi_topo` the real top?
- A person, a face or a hand is hard to draw well: show the object they use instead. An animal works as a head and paws built from ellipses and rounded shapes (see the dog).
- `montar.py` names what it refuses (a tag, an attribute, a class, an id, too few shapes): fix that line and run it again.
