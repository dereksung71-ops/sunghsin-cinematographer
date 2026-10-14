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

CREDIT_FIELDS = [
    ("role", "Role"),
    ("director", "Directed by"),
    ("client", "Client"),
    ("year", "Year"),
    ("format", "Format"),
]

esc = html.escape


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


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
                preferred = [v for v in videos if v.stem.lower() in ("video", "trailer")]
                videos = preferred + [v for v in videos if v not in preferred]
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
    for key, value in tokens.items():
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
    return [(label, members) for _, label, members in groups]


def build_works_list(projects, root):
    blocks = []
    for label, members in group_by_category(projects):
        items = [
            '        <li><a href="{root}{slug}/index.html" data-slug="{slug}">{title}</a></li>'.format(
                root=root, slug=p["slug"], title=esc(p["title"])
            )
            for p in members
        ]
        blocks.append(
            '      <div class="works-group">\n'
            '        <h2 class="works-group-label label">{label}</h2>\n'
            '        <ul>\n{items}\n        </ul>\n'
            "      </div>".format(label=esc(label), items="\n".join(items))
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
    for label, members in group_by_category(projects):
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


def build_intro_html(intro_text):
    if not intro_text:
        return ""
    return '<div class="project-intro"><p>{}</p></div>'.format(esc(intro_text))


def build_credits_html(info):
    parts = []
    for key, label in CREDIT_FIELDS:
        value = str(info.get(key, "")).strip()
        if value:
            parts.append(
                '  <div class="credit"><dt>{}</dt><dd>{}</dd></div>'.format(label, esc(value))
            )
    return "\n".join(parts)


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
            '    <li><span class="contact-label">Email</span>'
            '<a href="mailto:{0}">{0}</a></li>'.format(email)
        )
    insta = contact.get("instagram")
    if insta:
        rows.append(
            '    <li><span class="contact-label">Instagram</span>'
            '<a href="{}" target="_blank" rel="noopener">{}</a></li>'.format(
                esc(insta["url"]), esc(insta.get("handle", insta["url"]))
            )
        )
    return "\n".join(rows)


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
                "INTRO_HTML": build_intro_html(p["info"].get("intro", "")),
                "CREDITS_HTML": build_credits_html(p["info"]),
                "STILLS_HTML": build_stills_html(p["stills"], "../"),
                "HEAD_EXTRA": vimeo_page_extras("../", bool(p["vimeo"]))[0],
                "VIMEO_SCRIPTS": vimeo_page_extras("../", bool(p["vimeo"]))[1],
            }),
        )

    print("Built {} film page(s) into {}".format(len(projects), DIST_DIR))
    for p in projects:
        print("  /{}/  [{}]  {} stills".format(p["slug"], p["category_label"], len(p["stills"])))


if __name__ == "__main__":
    main()
