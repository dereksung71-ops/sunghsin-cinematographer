# Portfolio site

Custom-coded, inspired by mac-scott.com's structure and restraint. See
`../portfolio-site-build-brief.md` for the original brief.

## How it works

`python3 build.py` (Python standard library only — no Node needed) reads
the folders under `assets/` and writes the finished site into `dist/`.
Your original files are never modified or renamed; the build copies them
into `dist/media/<slug>/` under clean web-safe names (`trailer.mp4`,
`still-01.jpg`, ...), so spaces, Chinese characters and symbols in your
filenames never end up in a URL.

## Adding or editing a film

Each film is one folder: `assets/<Category>/<Film Title>/`

```
assets/
  Narrative/                  ← category folder = section on Selected Works
    LUV/                      ← folder name = film title (and the URL: /luv/)
      info.json               ← text shown on the page (see below)
      video/video.mp4         ← the trailer (one .mp4)
      stills/stills1.jpg ...  ← stills, shown in natural filename order
  Documentary/
  Ads for Brands/
  Collaboration with Artist/
  css/  js/  images/  videos/ ← site files (home/contact media) — not films
```

- **New film**: make `assets/<Category>/<Title>/` with `video/` and
  `stills/` inside, add an `info.json`, run `python3 build.py`.
- **New category**: just make a new folder next to `Narrative`. Sections
  appear in this order: Narrative, Documentary, Ads for Brands,
  Collaboration with Artist (set in `CATEGORY_ORDER` in `build.py`); any
  other category folder follows alphabetically.
- **Stills** keep their own proportions (the build reads each image's
  size), so mixed 16:9 / 2.35:1 / 4:3 stills sit side by side correctly.
  Order is by filename, numbers counted properly (`2` before `10`).
- **Video** must be H.264 `.mp4` (not `.mov`/HEVC — browsers can't play
  those reliably). It autoplays muted and looped with no player controls.
  Browsers only allow autoplay when muted, so the trailer is silent.
- Trailers may be `.mp4` or H.264 `.mov`. The build copies each one into
  `dist` with its index moved to the front of the file (lossless — no
  re-encoding; your originals are never touched), so browsers can start
  playing before the whole file has downloaded.
- The Selected Works hover-preview uses the first still as the poster.

### Chinese / English

The site is bilingual: short labels (categories, navigation, credit
fields, festival and award names) always show a small Chinese companion;
long text (the film intros) follows the **EN / 中** switch at the top right. The choice is
remembered; first visit follows the browser language. Add `?lang=zh` to any
link to open it in Chinese.

- UI words, category names, roles and formats live in `data/i18n.json`
  (edit the Chinese there; add a new role/format and it shows up everywhere).
- Per film, in `info.json`: `"titleZh"` (Chinese title, shown under the
  title and beside it in the list), `"directorZh"` (Chinese name shown next
  to the director's name), `"introZh"` (Chinese intro; falls back to the
  English if missing), and `"awards"`.
- The director is shown large under the title; a film whose role is
  "Director" and has no `"director"` shows Sung Hsin as its director.

- `"onFilm": true` adds a **[Film 底片拍攝]** marker before the title in the
  Selected Works list (currently Existence, As I Saw Her, Sound of Wheel).
- On the home page the Chinese is set at about 0.78× the English size so the
  glyphs are as tall as the English capitals (a Chinese character at the same
  font-size looks about 1.4× taller).

### Festivals & awards

```json
"awards": [
  { "status": "winner", "year": 2025,
    "festival": { "zh": "金穗獎", "en": "Golden Harvest Awards" },
    "detail":   { "zh": "最佳學生劇情片", "en": "Best Student Fiction Film" } }
]
```

`status` is `winner` (榮獲, marked with a white bar), `selection` (入圍) or
`screening` (放映). `detail` is optional. Listed in the order written.

### Vimeo instead of a local file

Add the video's Vimeo id (the number in `vimeo.com/<id>`) to the film's
`info.json`:

```json
"vimeo": "1235832534",
"vimeoAspect": 1.7778
```

`vimeoAspect` is width ÷ height of the Vimeo video (1.7778 = 16:9). The
film page then plays the Vimeo video automatically on open (muted, looped,
no controls), and Selected Works plays it when you hover the title; the
player is created on the first hover and paused when you move away.

- The video must be **Public** on Vimeo and embeddable on your domain
  ("Where can this be embedded?" → anywhere, or your real domain).
  A private video shows nothing, so the page falls back (below).
- **Fallback**: if the Vimeo player doesn't start within ~10 seconds
  (private video, Vimeo down, blocked), the page plays the film's local
  `video/` file instead — as long as one is still in the folder. Delete the
  local file once you trust Vimeo to stop publishing it (smaller site);
  without it, a failed Vimeo shows just the poster still.
- The home hero works the same way: `"vimeo"` / `"vimeoAspect"` inside
  `"home"` in `data/site.json`.
- Film pages show the whole frame (never cropped); the home hero and the
  hover preview are full-bleed (cropped to fill).

### `info.json`

```json
{
  "role": "Cinematographer",
  "director": "Duan",
  "client": "",
  "year": "2025",
  "format": "Fiction Short",
  "intro": "It's not a love story."
}
```

Every field is optional; empty ones are simply not shown. Extras:
`"title"` (display name, if different from the folder name) and
`"order"` (position within its category; default is newest year first).

## Home and contact pages — `data/site.json`

```json
"siteName": "Sung Hsin / Cinematographer",
"home":    { "video": "/assets/videos/home/hero.mp4", "poster": "/assets/images/home/hero-poster.jpg" },
"contact": {
  "image": "/assets/images/contact/background.jpg",
  "email": "you@example.com",
  "instagram": { "url": "https://www.instagram.com/...", "handle": "@..." }
}
```

- `siteName` shows on the Home page, and top-right on every other page
  (where it links back to Home).
- The home hero video is `assets/videos/home/hero.mp4`; its poster frame
  is `assets/images/home/hero-poster.jpg`.
- Contact is a full-screen photo with a 30% black layer, plus a mailto
  link and an Instagram link — there is no form and no server code.
  Change the layer's darkness in `style.css` (`.contact-bg-overlay`).
  `background.jpg` is a web-sized copy (2400px, ~1MB) of `photo_1.jpg`;
  the 15MB original can be moved out of the project to keep it light.

## Film order

Within a category, films sort by `"order"` in their `info.json`
(1 = first), then newest year. Currently: Narrative = Ready Serve Smash,
Pipedream, As I Saw Her, LUV; Collaboration with Artist = Sound of Wheel, ILY.

## Local preview

Easiest: run `python3 build.py`, then in Finder open the `dist` folder and
double-click `index.html`. All links and media paths are relative, so the
site works as plain files — no server needed — and you can click through
every page.

Or with a local server that never caches (always shows the latest build):

```bash
python3 serve.py
```

then open http://localhost:8000.

## Live site (GitHub Pages)

**https://dereksung71-ops.github.io/sunghsin-cinematographer/**

Source: https://github.com/dereksung71-ops/sunghsin-cinematographer (public).
Every push to the `main` branch triggers `.github/workflows/pages.yml`,
which runs `python3 build.py` on GitHub's servers and publishes `dist/`
(takes about 2–3 minutes; progress under the repo's *Actions* tab).

To publish a change: edit files, then `git add -A`, `git commit`,
`git push` (or ask Claude to). The first publish uploaded ~700MB; later
pushes only upload what changed.

GitHub Pages limits: published site under 1GB (currently ~640MB), about
100GB bandwidth per month, single files under 100MB. Once the Vimeo
trailers are trusted, deleting the local copies of the films that use them
(see the Vimeo section) makes the site and every upload much smaller.

Heads-up: GitHub rejects files over 100MB, and the repo currently holds
about 470MB of media. `ILY` (99MB) and `Corona` (95MB) trailers are right
at the limit — keep them from growing, or shrink them a bit more.

## Still placeholder

- `Apple Tree`, `Corona` etc. use their folder names as titles; add
  `"title"` to an `info.json` to change one.
- No favicon.
