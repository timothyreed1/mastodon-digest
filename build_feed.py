#!/usr/bin/env python3
"""
Rebuild atom.xml from the newest digest markdown file in OUT_DIR. The feed
carries that one entry; readers keep whatever they have already fetched.

Env:
  OUT_DIR      default output folder
  FEED_URL     public URL the feed will be served at
  FEED_AUTHOR  feed author name, default Mastodon Digest

Requires the `markdown` and `nh3` packages (nh3 sanitizes the rendered
digest HTML before it's embedded in the feed, since it's LLM output
summarizing untrusted third-party posts).
"""

import argparse
import glob
import os
import re
import tempfile
from datetime import datetime
from xml.sax.saxutils import escape

import markdown
import nh3

FEED_TITLE = "Mastodon Digest"
FEED_AUTHOR = os.environ.get("FEED_AUTHOR") or FEED_TITLE

# The digest body is LLM output summarizing posts from anyone in your
# timeline, so treat its rendered HTML as untrusted: prompt injection can
# coax a model into emitting raw markup. Sanitize to a plain formatting
# allowlist before it goes into the public feed.
ALLOWED_TAGS = {
    "p", "br", "strong", "em", "b", "i", "a", "ul", "ol", "li",
    "blockquote", "code", "pre", "h1", "h2", "h3", "h4", "h5", "h6", "hr",
}
ALLOWED_ATTRS = {"a": {"href"}}


def parse_note(path):
    with open(path) as f:
        raw = f.read()
    meta, body = {}, raw
    if raw.startswith("---\n"):
        end = raw.find("\n---\n", 4)
        if end != -1:
            for line in raw[4:end].splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            body = raw[end + 5:]
    title = meta.get("title") or os.path.splitext(os.path.basename(path))[0]
    try:
        dt = datetime.fromisoformat(meta["date"])
    except (KeyError, ValueError):
        dt = datetime.fromtimestamp(os.path.getmtime(path)).astimezone()
    return title, dt, body


URL_RE = re.compile(r'(?<![("<])\bhttps?://[^\s<>")]+')


def autolink(html_text):
    """Make bare URLs clickable. Skips ones already inside a tag or href."""
    parts = re.split(r"(<[^>]+>)", html_text)
    for i, part in enumerate(parts):
        if not part.startswith("<"):
            parts[i] = URL_RE.sub(lambda m: f'<a href="{m.group(0)}">{m.group(0)}</a>', part)
    return "".join(parts)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=os.environ.get("OUT_DIR", "/out"))
    ap.add_argument("--feed-url", default=os.environ.get("FEED_URL", ""))
    args = ap.parse_args()

    files = glob.glob(os.path.join(args.out_dir, "Mastodon Digest *.md"))
    if not files:
        return

    title, newest, body = parse_note(max(files, key=os.path.getmtime))
    content = autolink(
        markdown.markdown(body, extensions=["extra", "sane_lists"])
    )
    content = nh3.clean(content, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS)
    entries = [
        "  <entry>\n"
        f"    <title>{escape(title)}</title>\n"
        f"    <id>urn:masto-digest:{slug(title)}</id>\n"
        f"    <updated>{newest.isoformat(timespec='seconds')}</updated>\n"
        f"    <content type=\"html\">{escape(content)}</content>\n"
        "  </entry>"
    ]
    feed_url_text = escape(args.feed_url)
    feed_url_attr = escape(args.feed_url, {'"': "&quot;"})
    feed = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom">\n'
        f"  <title>{FEED_TITLE}</title>\n"
        f"  <id>{feed_url_text or 'urn:masto-digest:feed'}</id>\n"
        f"  <updated>{newest.isoformat(timespec='seconds')}</updated>\n"
        f'  <link rel="self" href="{feed_url_attr}"/>\n'
        f"  <author><name>{escape(FEED_AUTHOR)}</name></author>\n"
        + "\n".join(entries)
        + "\n</feed>\n"
    )

    dest = os.path.join(args.out_dir, "atom.xml")
    fd, tmp = tempfile.mkstemp(dir=args.out_dir, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        f.write(feed)
    os.replace(tmp, dest)
    os.chmod(dest, 0o644)  # scp preserves mode; Apache needs world-readable
    print(dest)


if __name__ == "__main__":
    main()
