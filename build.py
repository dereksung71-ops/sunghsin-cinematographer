#!/usr/bin/env python3
"""
Static site generator for the portfolio site (stdlib only, no Node needed).

Films are discovered straight from the folder structure under assets/:

    assets/<Category>/<Film Title>/
        video/   <- the trailer (one .mp4)
        stills/  <- the stills (.jpg / .png), shown in natural filename order
        info.json  <- optional: role, director, client, year, format, intro

The category folder decides the section on Selected Works; the film folder
name is the title (override with "title" in info.json). Media is copied to
dist/media/<slug>/ under clean web-safe names, so the original filenames
(spaces, Chinese, symbols) never reach a URL and are never modified.

Usage:
    python3 build.py
"""

import html
import json
import os
import re
import shutil
import struct
from pathlib import Path

ROOT_DIR = Path(__file__).parent
DATA_DIR = ROOT_DIR / "data"
TEMPLATES_DIR = ROOT_DIR / "templates"
ASSETS_DIR = ROOT_DIR / "assets"
DIST_DIR = ROOT_DIR / "dist"

ROW_HEIGHT = 220  # baseline px height used to derive still widths from aspect ratio
DEFAULT_ASPECT = 1.778
DEFAULT_VIDEO_ASPECT = 1.7778

# Top-level folders in assets/ that are site files, not film categories.
NON_CATEGORY_DIRS = {"css", "js", "images", "videos"}
# Categories are shown in this order; any other category folder follows alphabetically.
CATEGORY_ORDER = ["narrative", "documentary", "ads for brands", "collaboration with artist"]

# .mov is accepted (H.264 only) and published as .mp4 with type video/mp4.
VIDEO_TYPES = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm", ".mov": "video/mp4"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}

CREDIT_FIELDS = ["role", "client", "year", "format"]  # the director has its own block

esc = html.escape

# Sets <html data-lang> before first paint: ?lang=zh|en, else the saved choice,
# else the browser's language (any zh-* means Chinese).
LANG_BOOT = (
    "<script>(function(){try{var q=new URLSearchParams(location.search).get('lang');"
    "var l=(q==='zh'||q==='en')?q:localStorage.getItem('lang');"
    "if(!l){l=(navigator.language||'').toLowerCase().indexOf('zh')===0?'zh':'en'}"
    "document.documentElement.setAttribute('data-lang',l);"
    "document.documentElement.lang=l==='zh'?'zh-Hant':'en'}catch(e){}})();</script>"
)
LANG_SWITCH = (
    '<div class="lang-switch" role="group" aria-label="Language">'
    '<button type="button" data-set-lang="en">EN</button><span aria-hidden="true">/</span>'
    '<button type="button" data-set-lang="zh" lang="zh-Hant">中</button></div>'
)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


I18N = load_json(DATA_DIR / "i18n.json")


def zh_sub(zh):
    """Small Chinese text that follows an English label, always visible."""
    return ' <span class="zh-sub" lang="zh-Hant">{}</span>'.format(esc(zh)) if zh else ""


def bi(pair):
    en, zh = pair
    return esc(en) + zh_sub(zh)


def texts(en, zh=None, fallback=True):
    """Long text that switches with the language toggle. A missing Chinese
    version falls back to the English (unless fallback=False: Chinese mode then
    shows nothing, as for the hover hint)."""
    en, zh = (en or "").strip(), (zh or "").strip()
    if en and zh:
        return ('<span class="t-en" lang="en">{}</span>'
                '<span class="t-zh" lang="zh-Hant">{}</span>').format(esc(en), esc(zh))
    if en:
        cls = "t-any" if fallback else "t-en"
        return '<span class="{}" lang="en">{}</span>'.format(cls, esc(en))
    if zh:
        return '<span class="t-zh" lang="zh-Hant">{}</span>'.format(esc(zh))
    return ""


def brand_html():
    p = I18N["person"]
    return "{}{} / {}{}".format(esc(p["name"]), zh_sub(p["nameZh"]), esc(p["role"]), zh_sub(p["roleZh"]))


def global_tokens():
    ui = I18N["ui"]
    return {
        "LANG_BOOT": LANG_BOOT,
        "LANG_SWITCH": LANG_SWITCH,
        "BRAND_HTML": brand_html(),
        "NAV_HOME": bi(ui["home"]),
        "NAV_WORKS": bi(ui["selectedWork"]),
        "NAV_CONTACT": bi(ui["contact"]),
        "NAV_SEE_WORKS": bi(ui["seeSelectedWork"]),
        "NAV_CONTACT_CTA": bi(ui["contactCta"]),
        "HINT_HTML": texts(ui["hint"][0], ui["hint"][1], fallback=False),
    }


def natural_key(name):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def category_label(folder_name):
    return re.sub(r"\s*:\s*", " / ", folder_name)


def find_subdir(parent, name):
    for child in parent.iterdir():
        if child.is_dir() and child.name.lower() == name:
            return child
    return None


def image_size(path):
    """(width, height) of a JPEG/PNG read from its header, or None."""
    try:
        with open(path, "rb") as f:
            head = f.read(24)
            if head[:8] == b"\x89PNG\r\n\x1a\n":
                return struct.unpack(">II", head[16:24])
            if head[:2] != b"\xff\xd8":
                return None
            f.seek(2)
            while True:
                byte = f.read(1)
                while byte and byte != b"\xff":
                    byte = f.read(1)
                while byte == b"\xff":
                    byte = f.read(1)
                if not byte:
                    return None
                marker = byte[0]
                if marker == 0x01 or 0xD0 <= marker <= 0xD8:
                    continue
                if marker == 0xD9:
                    return None
                (length,) = struct.unpack(">H", f.read(2))
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                              0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    f.read(1)
                    height, width = struct.unpack(">HH", f.read(4))
                    return width, height
                f.seek(length - 2, 1)
    except (OSError, struct.error):
        return None


def parse_vimeo(raw, aspect):
    """{"id", "aspect"} from an info.json "vimeo" value (a bare id or a vimeo.com URL), or None."""
    match = re.search(r"\d{6,}", str(raw or ""))
    if not match:
        return None
    try:
        ratio = float(aspect) if aspect else DEFAULT_VIDEO_ASPECT
    except (TypeError, ValueError):
        ratio = DEFAULT_VIDEO_ASPECT
    return {"id": match.group(), "aspect": round(ratio, 4)}


def discover_projects():
    categories = [
        d for d in ASSETS_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".")
        and d.name.lower() not in NON_CATEGORY_DIRS
    ]

    def category_sort(d):
        name = d.name.lower()
        if name in CATEGORY_ORDER:
            return (0, CATEGORY_ORDER.index(name), name)
        return (1, 0, name)

    projects = []
    seen_slugs = {}
    for cat_dir in sorted(categories, key=category_sort):
        for film_dir in sorted(cat_dir.iterdir(), key=lambda p: natural_key(p.name)):
            if not film_dir.is_dir() or film_dir.name.startswith("."):
                continue

            info_path = film_dir / "info.json"
            info = load_json(info_path) if info_path.exists() else {}
            title = (info.get("title") or film_dir.name).strip()
            slug = slugify(title)
            if not slug:
                raise SystemExit("Can't make a URL from the title of {}".format(film_dir))
            if slug in seen_slugs:
                raise SystemExit(
                    "Two films would share the URL /{}/: {} and {}".format(
                        slug, seen_slugs[slug], film_dir
                    )
                )
            seen_slugs[slug] = film_dir

            video_dir = find_subdir(film_dir, "video")
            stills_dir = find_subdir(film_dir, "stills")

            videos = []
            if video_dir:
                videos = sorted(
                    (f for f in video_dir.iterdir()
                     if f.is_file() and not f.name.startswith(".")
                     and f.suffix.lower() in VIDEO_TYPES),
                    key=lambda p: natural_key(p.name),
                )
            stills = []
            if stills_dir:
                stills = sorted(
                    (f for f in stills_dir.iterdir()
                     if f.is_file() and not f.name.startswith(".")
                     and f.suffix.lower() in IMAGE_EXTS),
                    key=lambda p: natural_key(p.name),
                )

            if len(videos) > 1:
                # A file named video/trailer wins; otherwise the most recently added one.
                preferred = [v for v in videos if v.stem.lower() in ("video", "trailer")]
                rest = sorted((v for v in videos if v not in preferred), key=lambda v: -v.stat().st_mtime)
                videos = preferred + rest
                print("  note: {} has {} videos; using '{}' (name the one you want 'video.mp4')".format(
                    film_dir.relative_to(ASSETS_DIR), len(videos), videos[0].name))
            if not videos:
                print("  warning: no .mp4 in {}/video".format(film_dir.relative_to(ASSETS_DIR)))
            if not stills:
                print("  warning: no stills in {}/stills".format(film_dir.relative_to(ASSETS_DIR)))

            try:
                year = int(re.search(r"\d{4}", str(info.get("year", ""))).group())
            except AttributeError:
                year = 0

            vimeo = parse_vimeo(info.get("vimeo"), info.get("vimeoAspect"))

            projects.append({
                "vimeo": vimeo,
                "slug": slug,
                "title": title,
                "category": cat_dir.name,
                "category_label": category_label(cat_dir.name),
                "order": info.get("order", 999),
                "year": year,
                "info": info,
                "video_file": videos[0] if videos else None,
                "still_files": stills,
            })
    return projects


def _top_level_atoms(f, total):
    atoms, pos = [], 0
    while pos + 8 <= total:
        f.seek(pos)
        size, kind = struct.unpack(">I4s", f.read(8))
        if size == 1:
            size = struct.unpack(">Q", f.read(8))[0]
        elif size == 0:
            size = total - pos
        if size < 8:
            break
        atoms.append((pos, size, kind))
        pos += size
    return atoms


def _shift_chunk_offsets(moov, delta):
    """Add `delta` to every chunk offset (stco/co64) inside a moov atom's bytes."""
    containers = {b"moov", b"trak", b"mdia", b"minf", b"stbl"}

    def walk(start, end):
        pos = start
        while pos + 8 <= end:
            size, kind = struct.unpack(">I4s", moov[pos:pos + 8])
            if size < 8:
                break
            body = pos + 8
            if kind in containers:
                walk(body, pos + size)
            elif kind == b"stco":
                (count,) = struct.unpack(">I", moov[body + 4:body + 8])
                for i in range(count):
                    at = body + 8 + 4 * i
                    (v,) = struct.unpack(">I", moov[at:at + 4])
                    moov[at:at + 4] = struct.pack(">I", v + delta)
            elif kind == b"co64":
                (count,) = struct.unpack(">I", moov[body + 4:body + 8])
                for i in range(count):
                    at = body + 8 + 8 * i
                    (v,) = struct.unpack(">Q", moov[at:at + 8])
                    moov[at:at + 8] = struct.pack(">Q", v + delta)
            pos += size

    walk(8, len(moov))  # skip the moov atom's own header


def copy_video(src, dest):
    """Copy a video; if its index (moov) sits after the media data, rewrite the
    copy with the index first so browsers can start playing before the whole
    file has downloaded. Lossless — nothing is re-encoded; the source is untouched."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    total = src.stat().st_size
    try:
        with open(src, "rb") as f:
            atoms = _top_level_atoms(f, total)
            kinds = [a[2] for a in atoms]
            if b"moov" not in kinds or b"mdat" not in kinds or kinds.index(b"moov") < kinds.index(b"mdat"):
                copy_file(src, dest)
                return False
            moov_pos, moov_size, _ = atoms[kinds.index(b"moov")]
            if moov_size > 64 * 1024 * 1024:
                copy_file(src, dest)
                return False
            f.seek(moov_pos)
            moov = bytearray(f.read(moov_size))
            _shift_chunk_offsets(moov, moov_size)
            first_after_ftyp = atoms[kinds.index(b"ftyp") + 1][0] if b"ftyp" in kinds else 0
            with open(dest, "wb") as out:
                f.seek(0)
                out.write(f.read(first_after_ftyp))           # ftyp (+ anything before)
                out.write(moov)                               # index, now up front
                f.seek(first_after_ftyp)
                remaining = moov_pos - first_after_ftyp       # media data etc. up to old moov
                while remaining:
                    chunk = f.read(min(1 << 20, remaining))
                    out.write(chunk)
                    remaining -= len(chunk)
                f.seek(moov_pos + moov_size)
                shutil.copyfileobj(f, out, 1 << 20)           # anything after the old moov
        return True
    except (OSError, struct.error):
        if dest.exists():
            dest.unlink()
        copy_file(src, dest)
        return False


def copy_file(src, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dest)  # no duplicate bytes on disk when possible
    except OSError:
        shutil.copy2(src, dest)


def publish_media(project):
    """Copy a film's media into dist/media/<slug>/ and record its web paths."""
    slug = project["slug"]
    out_dir = DIST_DIR / "media" / slug

    project["video"] = None
    if project["video_file"]:
        ext = project["video_file"].suffix.lower()
        if ext == ".mov":
            ext = ".mp4"
        copy_video(project["video_file"], out_dir / ("trailer" + ext))
        project["video"] = {
            "src": "media/{}/trailer{}".format(slug, ext),
            "type": VIDEO_TYPES[ext],
        }

    stills = []
    for i, still in enumerate(project["still_files"], start=1):
        ext = still.suffix.lower().replace(".jpeg", ".jpg")
        name = "still-{:02d}{}".format(i, ext)
        copy_file(still, out_dir / name)
        size = image_size(still)
        aspect = round(size[0] / size[1], 3) if size and size[1] else DEFAULT_ASPECT
        stills.append({"src": "media/{}/{}".format(slug, name), "aspect": aspect})
    project["stills"] = stills
    project["poster"] = stills[0]["src"] if stills else ""


def render(template_name, tokens):
    text = (TEMPLATES_DIR / template_name).read_text(encoding="utf-8")
    merged = dict(global_tokens())
    merged.update(tokens)
    for key, value in merged.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def group_by_category(projects):
    groups = []
    for p in projects:
        if not groups or groups[-1][0] != p["category"]:
            groups.append((p["category"], p["category_label"], []))
        groups[-1][2].append(p)
    for _, _, members in groups:
        members.sort(key=lambda p: (p["order"], -p["year"], p["title"].lower()))
    return [(label, members, key.lower()) for key, label, members in groups]


def film_tag(info):
    """[Film 底片拍攝] marker for work shot on film ("onFilm": true in info.json)."""
    if not info.get("onFilm"):
        return ""
    return '<span class="work-tag">[{}]</span>'.format(bi(I18N["ui"]["onFilm"]))


def build_works_list(projects, root):
    blocks = []
    for label, members, key in group_by_category(projects):
        items = [
            '        <li><a href="{root}{slug}/index.html" data-slug="{slug}">{tag}{title}{zh}</a></li>'.format(
                root=root, slug=p["slug"], tag=film_tag(p["info"]), title=esc(p["title"]),
                zh=zh_sub(p["info"].get("titleZh"))
            )
            for p in members
        ]
        blocks.append(
            '      <div class="works-group">\n'
            '        <h2 class="works-group-label label">{label}{zh}</h2>\n'
            '        <ul>\n{items}\n        </ul>\n'
            "      </div>".format(label=esc(label), zh=zh_sub(I18N["categories"].get(key)), items="\n".join(items))
        )
    return "\n".join(blocks)


def vimeo_attrs(vimeo, video, root):
    """data-* attributes the page script needs: the Vimeo id, its aspect ratio,
    and (if the film also has a local video) a fallback for when Vimeo can't play."""
    attrs = 'data-vimeo="{}" style="--ar: {}"'.format(vimeo["id"], vimeo["aspect"])
    if video:
        attrs += ' data-fallback-src="{}{}" data-fallback-type="{}"'.format(
            root, video["src"], video["type"]
        )
    return attrs


def poster_img(poster, root):
    return '<img class="vimeo-poster" src="{}{}" alt="">'.format(root, poster) if poster else ""


def build_preview_elements(projects, root):
    els = []
    for label, members, key in group_by_category(projects):
        for p in members:
            if p["vimeo"]:
                els.append(
                    '    <div class="preview-vimeo vimeo-cover" data-slug="{slug}" {attrs}>{img}</div>'.format(
                        slug=p["slug"],
                        attrs=vimeo_attrs(p["vimeo"], p["video"], root),
                        img=poster_img(p["poster"], root),
                    )
                )
            elif p["video"]:
                els.append(
                    '    <video data-slug="{slug}" muted loop playsinline preload="none" '
                    'poster="{root}{poster}"><source src="{root}{src}" type="{type}"></video>'.format(
                        slug=p["slug"], root=root, poster=p["poster"], **p["video"]
                    )
                )
            elif p["poster"]:
                els.append(
                    '    <img data-slug="{slug}" src="{root}{poster}" alt="">'.format(
                        slug=p["slug"], root=root, poster=p["poster"]
                    )
                )
    return "\n".join(els)


def build_hero_media_html(p, root):
    if p["vimeo"]:
        return '<div class="vimeo-hero vimeo-contain vimeo-auto" {attrs}>{img}</div>'.format(
            attrs=vimeo_attrs(p["vimeo"], p["video"], root), img=poster_img(p["poster"], root)
        )
    if p["video"]:
        return (
            '<video autoplay muted loop playsinline poster="{root}{poster}">'
            '<source src="{root}{src}" type="{type}"></video>'.format(
                root=root, poster=p["poster"], **p["video"]
            )
        )
    if p["poster"]:
        return '<img src="{}{}" alt="">'.format(root, p["poster"])
    return ""


def build_home_media_html(home):
    """Home hero (page lives at the site root, so paths need no prefix)."""
    video_path = home.get("video", "").lstrip("/")
    poster = home.get("poster", "").lstrip("/")
    if video_path and not (ASSETS_DIR.parent / video_path).exists():
        # The configured file is missing (renamed?): use whatever video sits in that folder.
        folder = (ASSETS_DIR.parent / video_path).parent
        found = sorted(f for f in folder.glob("*") if f.suffix.lower() in VIDEO_TYPES) if folder.is_dir() else []
        if found:
            video_path = found[0].relative_to(ASSETS_DIR.parent).as_posix()
            print("  note: home video not found at the configured path; using {}".format(video_path))
    has_video = bool(video_path) and (ASSETS_DIR.parent / video_path).exists()
    fallback = {"src": video_path, "type": "video/mp4"} if has_video else None
    vimeo = parse_vimeo(home.get("vimeo"), home.get("vimeoAspect"))
    if vimeo:
        return '<div class="home-vimeo vimeo-cover vimeo-auto" {attrs}>{img}</div>'.format(
            attrs=vimeo_attrs(vimeo, fallback, ""), img=poster_img(poster, "")
        )
    if has_video:
        return (
            '<video class="home-video" autoplay muted loop playsinline poster="{}">'
            '<source src="{}" type="video/mp4"></video>'.format(poster, video_path)
        )
    return poster_img(poster, "")


def vimeo_page_extras(root, used):
    """Head hints + script tag, only on pages that actually embed Vimeo."""
    if not used:
        return "", ""
    head = (
        '<link rel="preconnect" href="https://player.vimeo.com">\n'
        '<link rel="preconnect" href="https://f.vimeocdn.com">'
    )
    return head, '<script src="{}assets/js/vimeo.js"></script>'.format(root)


def credit_value(key, value):
    if key == "role":
        return esc(value) + zh_sub(I18N["roles"].get(value))
    if key == "format":
        parts = [x.strip() for x in value.split("/") if x.strip()]
        return " / ".join(esc(x) + zh_sub(I18N["formats"].get(x)) for x in parts)
    return esc(value)


def build_director_html(info):
    name = str(info.get("director", "")).strip()
    if name:
        who = esc(name) + zh_sub(info.get("directorZh"))
    elif str(info.get("role", "")).strip().lower() == "director":
        who = esc(I18N["person"]["name"]) + zh_sub(I18N["person"]["nameZh"])
    else:
        return ""
    return (
        '<div class="project-director"><span class="project-director-label">{}</span>'
        '<span class="project-director-name">{}</span></div>'.format(bi(I18N["credits"]["director"]), who)
    )


def pair_html(d):
    """English text followed by its Chinese companion (either may be missing)."""
    en = str((d or {}).get("en", "")).strip()
    zh = str((d or {}).get("zh", "")).strip()
    return esc(en) + zh_sub(zh) if en else esc(zh)


def build_awards_html(awards):
    if not awards:
        return ""
    items = []
    for a in awards:
        status = a.get("status", "selection")
        items.append(
            '    <li class="award award-{status}">'
            '<span class="award-status">{label}</span>'
            '<span class="award-year">{year}</span>'
            '<span class="award-body"><span class="award-festival">{festival}</span>'
            '<span class="award-detail">{detail}</span></span></li>'.format(
                status=esc(status),
                label=bi(I18N["ui"].get(status, I18N["ui"]["selection"])),
                year=esc(str(a.get("year", ""))),
                festival=pair_html(a.get("festival")),
                detail=pair_html(a.get("detail")),
            )
        )
    return (
        '<section class="project-awards">\n'
        '  <h2 class="project-awards-title label">{}</h2>\n  <ul>\n{}\n  </ul>\n</section>'.format(
            bi(I18N["ui"]["festivals"]), "\n".join(items)
        )
    )


def build_info_html(p):
    info = p["info"]
    meta = [
        '<h1 class="project-title">{}{}</h1>'.format(esc(p["title"]), zh_sub(info.get("titleZh"))),
        build_director_html(info),
        build_credits_html(info),
    ]
    story = []
    intro = texts(info.get("intro"), info.get("introZh"))
    if intro:
        story.append('<p class="project-intro-text">{}</p>'.format(intro))
    awards = build_awards_html(info.get("awards"))
    if awards:
        story.append(awards)
    return (
        '<div class="project-info">\n<div class="project-meta">\n{}\n</div>\n'
        '<div class="project-story">\n{}\n</div>\n</div>'.format(
            "\n".join(x for x in meta if x), "\n".join(story)
        )
    )


def build_credits_html(info):
    rows = []
    for key in CREDIT_FIELDS:
        value = str(info.get(key, "")).strip()
        if value:
            rows.append(
                '  <div class="credit"><dt>{}</dt><dd>{}</dd></div>'.format(
                    bi(I18N["credits"][key]), credit_value(key, value)
                )
            )
    return '<dl class="project-credits">\n{}\n</dl>'.format("\n".join(rows)) if rows else ""


def build_stills_html(stills, root):
    parts = []
    for still in stills:
        aspect = still["aspect"]
        basis = round(aspect * ROW_HEIGHT)
        style = "aspect-ratio: {a}; flex-basis: {b}px; flex-grow: {a};".format(a=aspect, b=basis)
        parts.append(
            '  <div class="still" style="{}"><img src="{}{}" alt="" loading="lazy"></div>'.format(
                style, root, still["src"]
            )
        )
    return "\n".join(parts)


def build_contact_links_html(contact):
    rows = []
    if contact.get("email"):
        email = esc(contact["email"])
        rows.append(
            '    <li><span class="contact-label">{1}</span>'
            '<a href="mailto:{0}">{0}</a></li>'.format(email, bi(I18N["ui"]["email"]))
        )
    insta = contact.get("instagram")
    if insta:
        rows.append(
            '    <li><span class="contact-label">{}</span>'
            '<a href="{}" target="_blank" rel="noopener">{}</a></li>'.format(
                bi(I18N["ui"]["instagram"]), esc(insta["url"]), esc(insta.get("handle", insta["url"]))
            )
        )
    return "\n".join(rows)


VIMEO_CHECK_PAGE = """<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Vimeo check</title>
<style>
  body { margin: 0; padding: 40px 24px; background: #000; color: #ddd; font: 14px/1.6 -apple-system, "PingFang TC", "Helvetica Neue", sans-serif; }
  h1 { margin: 0 0 6px; font-size: 20px; font-weight: 400; color: #fff; }
  p { max-width: 640px; color: #999; }
  table { border-collapse: collapse; margin-top: 24px; width: 100%; max-width: 760px; }
  td, th { padding: 9px 12px; border-bottom: 1px solid #222; text-align: left; }
  th { color: #777; font-weight: 400; font-size: 12px; }
  .ok { color: #7ddf8a; } .bad { color: #ff7b7b; } .wait { color: #999; }
  a { color: #8ab4ff; }
  #summary { margin-top: 24px; font-size: 16px; color: #fff; }
</style></head><body>
<h1>Vimeo 檢查頁</h1>
<p>這一頁會逐支測試網站上用到的 Vimeo 影片能不能在「這台電腦」播放。每支最多等 12 秒，全部測完會顯示總結。
測完請把畫面截圖給 Claude。</p>
<div id="summary">測試中…</div>
<table><thead><tr><th>位置</th><th>Vimeo ID</th><th>結果</th><th>時間</th></tr></thead><tbody id="rows"></tbody></table>
<script src="../assets/js/vimeo.js"></script>
<script>
const ITEMS = __ITEMS__;
const tbody = document.getElementById("rows"), summary = document.getElementById("summary");
const rows = ITEMS.map(function (it) {
  const tr = document.createElement("tr");
  tr.innerHTML = '<td></td><td><a target="_blank" rel="noopener" href="https://vimeo.com/' + it[1] + '">' + it[1] + '</a></td><td class="wait">等待中</td><td></td>';
  tr.children[0].textContent = it[0]; tbody.appendChild(tr); return tr;
});
(async function () {
  let ok = 0;
  for (let i = 0; i < ITEMS.length; i++) {
    const tr = rows[i], t0 = Date.now();
    tr.children[2].textContent = "測試中…";
    const holder = document.createElement("div");
    holder.style.cssText = "position:fixed;left:-9999px;top:0;width:320px;height:180px";
    document.body.appendChild(holder);
    try {
      const r = await window.PortfolioVimeo.mount(holder, ITEMS[i][1], 12000);
      tr.children[2].className = "ok"; tr.children[2].textContent = "✓ 正常"; ok++;
      try { await r.player.pause(); r.player.destroy(); } catch (e) {}
    } catch (e) {
      tr.children[2].className = "bad"; tr.children[2].textContent = "✗ 失敗（" + (e.message || "error") + "）";
    }
    tr.children[3].textContent = ((Date.now() - t0) / 1000).toFixed(1) + " 秒";
    holder.remove();
  }
  summary.textContent = "結果：" + ok + " / " + ITEMS.length + " 支能正常播放　（" + new Date().toLocaleString() + "）";
})();
</script></body></html>
"""


def write_vimeo_check(site, projects):
    items = []
    if site.get("home", {}).get("vimeo"):
        items.append(["首頁 Home", str(site["home"]["vimeo"])])
    for p in projects:
        if p["vimeo"]:
            items.append([p["title"], p["vimeo"]["id"]])
    page = VIMEO_CHECK_PAGE.replace("__ITEMS__", json.dumps(items, ensure_ascii=False))
    write(DIST_DIR / "vimeo-check" / "index.html", page)


def copy_site_assets():
    """Copy css/js/images/videos, but not the film folders (those are published
    separately, renamed, under dist/media/)."""
    def ignore(directory, names):
        skipped = {n for n in names if n == ".DS_Store"}
        if Path(directory) == ASSETS_DIR:
            skipped |= {
                n for n in names
                if (Path(directory) / n).is_dir() and n.lower() not in NON_CATEGORY_DIRS
            }
        return skipped

    shutil.copytree(ASSETS_DIR, DIST_DIR / "assets", ignore=ignore)
    for video in (DIST_DIR / "assets" / "videos").rglob("*"):
        if video.is_file() and video.suffix.lower() in (".mp4", ".m4v", ".mov"):
            original = ASSETS_DIR / video.relative_to(DIST_DIR / "assets")
            video.unlink()
            copy_video(original, video)


def main():
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True)

    site = load_json(DATA_DIR / "site.json")
    projects = discover_projects()
    copy_site_assets()
    for p in projects:
        publish_media(p)

    write(
        DIST_DIR / "index.html",
        render("home.html", {
            "ROOT": "",
            "SITE_NAME": esc(site["siteName"]),
            "HERO_MEDIA_HTML": build_home_media_html(site["home"]),
            "HEAD_EXTRA": vimeo_page_extras("", bool(site["home"].get("vimeo")))[0],
            "VIMEO_SCRIPTS": vimeo_page_extras("", bool(site["home"].get("vimeo")))[1],
        }),
    )

    write(
        DIST_DIR / "selected-works" / "index.html",
        render("selected-works.html", {
            "ROOT": "../",
            "SITE_NAME": esc(site["siteName"]),
            "WORKS_LIST": build_works_list(projects, "../"),
            "PREVIEW_ELEMENTS": build_preview_elements(projects, "../"),
            "HEAD_EXTRA": vimeo_page_extras("../", any(p["vimeo"] for p in projects))[0],
            "VIMEO_SCRIPTS": vimeo_page_extras("../", any(p["vimeo"] for p in projects))[1],
        }),
    )

    contact = site.get("contact", {})
    write(
        DIST_DIR / "contact" / "index.html",
        render("contact.html", {
            "ROOT": "../",
            "SITE_NAME": esc(site["siteName"]),
            "CONTACT_IMAGE": "../" + contact.get("image", "").lstrip("/"),
            "CONTACT_LINKS_HTML": build_contact_links_html(contact),
        }),
    )

    for p in projects:
        write(
            DIST_DIR / p["slug"] / "index.html",
            render("project.html", {
                "ROOT": "../",
                "SITE_NAME": esc(site["siteName"]),
                "TITLE": esc(p["title"]),
                "HERO_MEDIA_HTML": build_hero_media_html(p, "../"),
                "INFO_HTML": build_info_html(p),
                "STILLS_HTML": build_stills_html(p["stills"], "../"),
                "HEAD_EXTRA": vimeo_page_extras("../", bool(p["vimeo"]))[0],
                "VIMEO_SCRIPTS": vimeo_page_extras("../", bool(p["vimeo"]))[1],
            }),
        )

    write_vimeo_check(site, projects)
    print("Built {} film page(s) into {}".format(len(projects), DIST_DIR))
    for p in projects:
        print("  /{}/  [{}]  {} stills".format(p["slug"], p["category_label"], len(p["stills"])))


if __name__ == "__main__":
    main()
