#!/usr/bin/env python3
"""
Fetch the last N hours of a Mastodon home timeline, summarize it, and
write a markdown digest into OUT_DIR.

Variables to set in the .env file:
  MASTODON_INSTANCE  instance base URL, e.g. https://hachyderm.io
  MASTODON_TOKEN     token from <instance>/settings/applications
  OPENAI_API_KEY     when --provider openai (default)
  ANTHROPIC_API_KEY  when --provider anthropic
  MASTODON_PRIORITY  optional comma separated Mastodon handles to always surface
  DIGEST_HOURS       hours of timeline to summarize, --hours overrides
  OUT_DIR            output folder
  TZ                 Set to your local timezone (e.g., America/New_York). Derived if not set

Providers:
  openai     https://api.openai.com
  anthropic  https://api.anthropic.com
  ollama     http://localhost:11434, no key needed
"""

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

import requests

PROVIDERS = {
    "openai": {
        "url": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o-mini",
        "key_env": "OPENAI_API_KEY",
    },
    "anthropic": {
        "url": "https://api.anthropic.com/v1/messages",
        "model": "claude-haiku-4-5-20251001",
        "key_env": "ANTHROPIC_API_KEY",
    },
    "ollama": {
        "url": os.environ.get("OLLAMA_URL", "http://localhost:11434")
        + "/v1/chat/completions",
        "model": os.environ.get("OLLAMA_MODEL", "llama3.1:8b"),
        "key_env": None,
    },
}


# What gets ranked as must-read. DIGEST_INTERESTS in .env overrides this.
INTERESTS = os.environ.get("DIGEST_INTERESTS") or """
news, digital audio players, diy electronics, hacking
"""
INTERESTS = INTERESTS.strip()


def env_int(name: str):
    """Clean and return a whole number."""
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        sys.exit(f"{name} must be a whole number, got {raw!r}")


def parse_accounts(raw: str) -> set:
    """Handles you never want to miss, comma separated, @ optional."""
    return {a.lstrip("@").lower() for a in re.split(r"[,\s]+", raw or "") if a}


def normalize_instance(raw: str) -> str:
    """Trim and add a url so MASTODON_INSTANCE can be a bare hostname."""
    raw = (raw or "").strip().rstrip("/")
    if raw and not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    return raw


class _TextExtractor(HTMLParser):
    """Pulls plain text out of Mastodon's HTML, turning <br> and </p> into
    line breaks. HTMLParser decodes entities per text node from the real
    markup structure, so text a user typed literally (which Mastodon
    safely entity-escapes, e.g. "&lt;script&gt;") comes out as inert text
    here. A regex strip-then-unescape does this in the wrong order and can
    resurrect exactly that escaped text back into a live tag.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.chunks = []

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.chunks.append("\n")

    def handle_endtag(self, tag):
        if tag == "p":
            self.chunks.append("\n\n")

    def handle_data(self, data):
        self.chunks.append(data)


def strip_html(s: str) -> str:
    parser = _TextExtractor()
    parser.feed(s or "")
    parser.close()
    return "".join(parser.chunks).strip()


def fetch_timeline(instance: str, token: str, hours: int, max_pages: int = 20):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    headers = {"Authorization": f"Bearer {token}"}
    params = {"limit": 40}
    out, seen = [], set()

    for _ in range(max_pages):
        r = requests.get(
            f"{instance}/api/v1/timelines/home",
            headers=headers,
            params=params,
            timeout=30,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break

        oldest = None
        for item in batch:
            oldest = item["id"]
            status = item.get("reblog") or item
            created = datetime.fromisoformat(
                status["created_at"].replace("Z", "+00:00")
            )
            if created < cutoff:
                continue
            if status["id"] in seen:
                continue
            seen.add(status["id"])
            out.append({
                "id": status["id"],
                "author": status["account"]["acct"],
                "url": status["url"],
                "boosted_by": item["account"]["acct"] if item.get("reblog") else None,
                "cw": status.get("spoiler_text") or "",
                "text": strip_html(status["content"]),
                "link": (status.get("card") or {}).get("url"),
                "link_title": (status.get("card") or {}).get("title"),
                "favs": status.get("favourites_count", 0),
                "boosts": status.get("reblogs_count", 0),
                "is_reply": bool(status.get("in_reply_to_id")),
            })

        last = datetime.fromisoformat(
            (batch[-1].get("reblog") or batch[-1])["created_at"].replace("Z", "+00:00")
        )
        if last < cutoff:
            break
        params["max_id"] = oldest

    return out


def render_corpus(posts, priority: set) -> str:
    lines = []
    for p in posts:
        meta = f"[{p['id']}] @{p['author']}"
        if p["boosted_by"]:
            meta += f" (boosted by @{p['boosted_by']})"
        if p["author"].lower() in priority:
            meta += " [PRIORITY]"
        meta += f" | {p['favs']}fav {p['boosts']}bst"
        if p["is_reply"]:
            meta += " | reply"
        lines.append(meta)
        if p["cw"]:
            lines.append(f"CW: {p['cw']}")
        lines.append(p["text"][:1200])
        if p["link"]:
            lines.append(f"LINK: {p['link_title']} {p['link']}")
        lines.append(f"URL: {p['url']}")
        lines.append("")
    return "\n".join(lines)


def summarize(corpus: str, hours: int, provider: str, api_key: str):
    prompt = f"""Below is my Mastodon home timeline from the last {hours} hours,
one post per block with an id in brackets.

My interests: {INTERESTS}

Produce, in markdown:

1. A section per theme (3 to 6 themes). One or two sentences each briefly summarizing what was said by each and by which accounts.
2. A "Must read" list of 5 to 10 posts, each as a single line: what the post is in 12 words or fewer, then the URL. Rank by relevance to my interests and by substance (analysis, a link worth opening, an announcement) over chatter.
 
Rules: No preamble, closing remarks, or explanations of why something matters. 
Do not pad. 
Plain, factual, terse. Report what posts say; do not evaluate them. 
No superlatives or praise words (e.g. "fascinating", "important", "notable", "great", "key", "significant", "urgent"). 
No intensifiers ("very", "really", "highly"). 
Weight content over engagement. 
If a post is a reply without visible context, ignore it unless it stands alone. 
Never fabricate a URL; only use URLs present below. 
Do not use Obsidian wikilink syntax. Write every link as a markdown link, never a bare URL.

TIMELINE:
{corpus}
"""
    return call_model(prompt, provider, api_key)


def call_model(prompt: str, provider: str, api_key: str):
    """Returns (text, {input_tokens, output_tokens})."""
    cfg = PROVIDERS[provider]

    if provider == "anthropic":
        r = requests.post(
            cfg["url"],
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": cfg["model"],
                "max_tokens": 4000,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=300,
        )
        r.raise_for_status()
        data = r.json()
        text = "".join(
            b.get("text", "") for b in data["content"] if b["type"] == "text"
        )
        u = data.get("usage", {})
        return text, {
            "input_tokens": u.get("input_tokens"),
            "output_tokens": u.get("output_tokens"),
        }

    # openai and ollama both speak the chat/completions shape
    headers = {"content-type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    r = requests.post(
        cfg["url"],
        headers=headers,
        json={
            "model": cfg["model"],
            "max_tokens": 4000,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=300,
    )
    r.raise_for_status()
    data = r.json()
    text = data["choices"][0]["message"]["content"]
    u = data.get("usage", {})
    return text, {
        "input_tokens": u.get("prompt_tokens"),
        "output_tokens": u.get("completion_tokens"),
    }


def atomic_write(path: str, content: str):
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        f.write(content)
    os.replace(tmp, path)
    os.chmod(path, 0o644)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=env_int("DIGEST_HOURS"))
    ap.add_argument("--out-dir", default=os.environ.get("OUT_DIR", "/out"))
    ap.add_argument(
        "--provider",
        default=os.environ.get("PROVIDER", "openai"),
        choices=sorted(PROVIDERS),
    )
    ap.add_argument("--model", help="override the provider default model")
    args = ap.parse_args()

    if args.model:
        PROVIDERS[args.provider]["model"] = args.model

    key_env = PROVIDERS[args.provider]["key_env"]
    instance = normalize_instance(os.environ.get("MASTODON_INSTANCE", ""))
    priority = parse_accounts(os.environ.get("MASTODON_PRIORITY", ""))
    token = os.environ.get("MASTODON_TOKEN")
    api_key = os.environ.get(key_env) if key_env else None
    if args.hours is None:
        sys.exit("Set DIGEST_HOURS in .env, or pass --hours")
    if not instance:
        sys.exit("Set MASTODON_INSTANCE, e.g. https://hachyderm.io")
    if not token:
        sys.exit("Set MASTODON_TOKEN")
    if key_env and not api_key:
        sys.exit(f"Set {key_env} for --provider {args.provider}")

    posts = fetch_timeline(instance, token, args.hours)
    if not posts:
        print("No posts in window, nothing written", file=sys.stderr)
        return

    now = datetime.now().astimezone()
    stamp = now.strftime("%Y-%m-%d %H%M")
    title = f"Mastodon Digest {stamp}"
    path = os.path.join(args.out_dir, f"{title}.md")

    body, usage = summarize(
        render_corpus(posts, priority), args.hours, args.provider, api_key
    )

    doc = (
        "---\n"
        f"title: {title}\n"
        f"date: {now.isoformat(timespec='seconds')}\n"
        "type: digest\n"
        "source: mastodon\n"
        f"window_hours: {args.hours}\n"
        f"post_count: {len(posts)}\n"
        "tags: [digest/mastodon]\n"
        "---\n\n"
        f"{body}\n"
    )

    atomic_write(path, doc)
    print(json.dumps({
        "file": path,
        "posts": len(posts),
        "provider": args.provider,
        "model": PROVIDERS[args.provider]["model"],
        **usage,
    }))


if __name__ == "__main__":
    main()
