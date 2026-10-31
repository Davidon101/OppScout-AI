# Vendored scripts

| File | Source | Version | Licence | SHA-256 |
|---|---|---|---|---|
| `htmx.min.js` | npm package `htmx.org`, `dist/htmx.min.js` | 2.0.4 | 0BSD | `e209dda5c8235479f3166defc7750e1dbcd5a5c1808b7792fc2e6733768fb447` |

Self-hosted so the site does not depend on a third-party CDN at request time.
To upgrade: `npm pack htmx.org@<version>`, copy `package/dist/htmx.min.js`, update this table.

## Fonts (self-hosted)

- Bricolage Grotesque Variable and Public Sans Variable, from the npm packages `@fontsource-variable/bricolage-grotesque` and `@fontsource-variable/public-sans` (5.3.0). Both are licensed under the SIL Open Font License 1.1. Only the `wght` axis files for the latin, latin-ext and vietnamese subsets are included (the vietnamese subset carries the letters used in Yoruba names, such as ẹ and ọ).
