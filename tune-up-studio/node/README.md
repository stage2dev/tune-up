# Pinned HyperFrames

`hyperframes` is pinned to **0.9.6** (published 2026-11-02T20:56Z).

Why: it was the newest stable release at least 7 days old on 2026-11-10.
HyperFrames ships several releases a day, so the lockfile was generated with
`npm install --package-lock-only --ignore-scripts --before=2026-11-03`. Every
dependency in `package-lock.json` resolves from registry.npmjs.org with an
integrity hash.

Known issue: 0.9.6 pins `undici@7.25.0`, which `npm audit` flags (1 high,
1 moderate through `hyperframes`). The latest release (0.9.30) pins the same
version, so upgrading does not fix it.

## Safe install

Run in a copy of this folder, outside `~/.claude` if the sandbox protects it:

```sh
npm ci --ignore-scripts
npm audit signatures
```

No install script is needed. The only package with one is `esbuild`
(`postinstall: node install.js`), and esbuild works without it through its
platform package (`@esbuild/<platform>`). `hyperframes` has no install script.
Chrome is not downloaded at install time: `hyperframes browser ensure` downloads
it on demand into `~/.cache/hyperframes/chrome`.

Set these for every call:

```sh
export HYPERFRAMES_NO_TELEMETRY=1      # or DO_NOT_TRACK=1
export HYPERFRAMES_NO_UPDATE_CHECK=1   # no update check
export HYPERFRAMES_NO_AUTO_INSTALL=1   # no detached self-upgrade
export HYPERFRAMES_SKIP_SKILLS=1       # init must not install skills
```

Then use `npx --no-install hyperframes <command>`.

## Skills

The package bundles its skills. Read them by path, never install them:
`node_modules/hyperframes/dist/skills/` (`hyperframes`, `hyperframes-cli`,
`media-use`).

GSAP 3.15.0 is vendored at `node_modules/hyperframes/dist/vendor/npm/gsap@3.15.0/`
(GreenSock standard license). The bundled templates load GSAP from
cdn.jsdelivr.net.

## Do not run

- `hyperframes skills` (writes to the global `~/.claude/skills`)
- `hyperframes init` without `--skip-skills` or `HYPERFRAMES_SKIP_SKILLS=1`
- `hyperframes upgrade`, `cloud`, `lambda`, `cloudrun`, `publish`, `auth`,
  `billing`, `tts`, `models install`, `transcribe`
- `npm install` or `npm update` here (they bypass the lockfile)
- any install script, unless a later item proves it is needed
