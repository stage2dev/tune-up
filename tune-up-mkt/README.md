# tune-up-mkt

Marketing module for [tune-up](../README.md): guided connection of your own marketing accounts, campaign, content, SEO and preflight skills, and a guard that blocks or asks before writes to ad accounts and public posts.

Status: 0.1.0: skeleton + guard; account connection, skills and panel tab arrive in the next releases.

## Install

```
/plugin marketplace add stage2dev/tune-up
/plugin install tune-up-mkt@tune-up
```

Requires the core `tune-up` plugin.

## Guard

The guard is best effort, not a security boundary. It runs as a hook through Python, and when no Python 3.9+ is found it fails open (the action goes through), the same as the core plugin's guards.

## License

MIT, see [LICENSE](LICENSE).
