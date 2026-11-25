#!/usr/bin/env python3
"""Merge Obtainium packs and generate entries for repositories no pack covers."""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

import yaml

TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO_RE = re.compile(
    r"https?://(github\.com|codeberg\.org)/([\w.-]+)/([\w.-]+)", re.IGNORECASE
)
NOT_REPOS = {"releases", "issues", "pulls", "wiki", "blob", "tree", "actions"}
SETTINGS_KEYS = {
    "includePrereleases": False,
    "fallbackToOlderReleases": True,
    "filterReleaseTitlesByRegEx": "",
    "filterReleaseNotesByRegEx": "",
    "verifyLatestTag": False,
    "sortMethodChoice": "date",
    "useLatestAssetDateAsReleaseDate": False,
    "releaseTitleAsVersion": False,
    "trackOnly": False,
    "versionExtractionRegEx": "",
    "matchGroupToUse": "",
    "versionDetection": True,
    "releaseDateAsVersion": False,
    "useVersionCodeAsOSVersion": False,
    "apkFilterRegEx": "",
    "invertAPKFilter": False,
    "autoApkFilterByArch": True,
    "appName": "",
    "appAuthor": "",
    "shizukuPretendToBeGooglePlay": False,
    "allowInsecure": False,
    "exemptFromBackgroundUpdates": False,
    "skipUpdateNotifications": False,
    "refreshBeforeDownload": False,
    "includeZips": False,
    "zippedApkFilterRegEx": "",
}


def get(url, accept=None):
    req = urllib.request.Request(
        url, headers={"User-Agent": "obtainium-pack-generator"}
    )
    if accept:
        req.add_header("Accept", accept)
    if TOKEN and "api.github.com" in url:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8")
        except OSError as e:
            if attempt == 3:
                raise RuntimeError(f"fetch failed after 3 attempts: {url}: {e}") from e
            time.sleep(5 * attempt)


def fetch_file(src):
    if "path" in src:
        return get(
            f"https://api.github.com/repos/{src['repo']}/contents/{src['path']}",
            "application/vnd.github.raw",
        )
    return get(src["url"])


def norm(url):
    m = REPO_RE.match(url or "")
    if not m:
        return (url or "").lower().rstrip("/")
    return f"{m.group(1).lower()}/{m.group(2).lower()}/{re.sub(r'\.git$', '', m.group(3).lower())}"


def api_base(host, owner, repo):
    if host == "github.com":
        return f"https://api.github.com/repos/{owner}/{repo}"
    return f"https://codeberg.org/api/v1/repos/{owner}/{repo}"


def apps_from_json(text):
    data = json.loads(text)
    return data["apps"] if isinstance(data, dict) else data


def apps_from_deeplinks(text):
    apps = []
    for m in re.finditer(r"obtainium://app/(%7B.+?%7D)\)", text):
        apps.append(json.loads(urllib.parse.unquote(m.group(1))))
    return apps


def repos_from_page(text, default=""):
    """Repo URLs with the nearest preceding '##' heading as category (default if none)."""
    text = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text)
    out, cat = [], default
    for line in text.splitlines():
        h = re.match(r"^#{2,3}\s+(.+?)\s*$", line)
        if h:
            cat = h.group(1)
        for m in REPO_RE.finditer(line):
            if m.group(3).lower() not in NOT_REPOS:
                out.append((m.group(0).rstrip("."), cat))
    return out


def build_entry(url, category, report):
    m = REPO_RE.match(url)
    host, owner, repo = (
        m.group(1).lower(),
        m.group(2),
        re.sub(r"\.git$", "", m.group(3)),
    )
    base = api_base(host, owner, repo)
    try:
        meta = json.loads(get(base))
        rels = json.loads(get(base + "/releases?per_page=30"))
    except (RuntimeError, ValueError, KeyError) as e:
        report.append(f"skipped {url}: {e}")
        return None
    if not any(
        a["name"].lower().endswith(".apk") for r in rels for a in r.get("assets", [])
    ):
        report.append(f"skipped {url}: no release ships an APK (zips or nothing)")
        return None
    settings = dict(SETTINGS_KEYS)
    stable = any(
        not r.get("prerelease")
        and not r.get("draft")
        and any(a["name"].lower().endswith(".apk") for a in r.get("assets", []))
        for r in rels
    )
    settings["includePrereleases"] = not stable
    settings["about"] = meta.get("description") or ""
    return {
        "id": f"{owner}.{repo}".lower(),
        "url": f"https://{host}/{owner}/{repo}",
        "author": owner,
        "name": meta.get("name") or repo,
        "preferredApkIndex": 0,
        "additionalSettings": json.dumps(settings, separators=(",", ":")),
        "categories": [category] if category else [],
        "allowIdChange": True,
        "overrideSource": "GitHub" if host == "github.com" else "Codeberg",
    }


def write_readme_section(apps, path):
    by_cat = {}
    for a in apps:
        by_cat.setdefault((a.get("categories") or ["Uncategorized"])[0], []).append(a)
    body = [
        f"**{len(apps)} apps** in {len(by_cat)} categories. Descriptions and sources: [CATALOGUE.md](CATALOGUE.md).",
        "",
    ]
    for cat in sorted(by_cat):
        names = ", ".join(
            f"[{a['name']}]({a['url']})"
            for a in sorted(by_cat[cat], key=lambda x: x["name"].lower())
        )
        body += [f"**{cat}** ({len(by_cat[cat])}): {names}", ""]
    with open(path) as f:
        text = f.read()
    new = re.sub(
        r"(<!-- catalogue:start -->\n).*?(<!-- catalogue:end -->)",
        lambda m: m.group(1) + "\n".join(body) + m.group(2),
        text,
        flags=re.DOTALL,
    )
    if new == text and "<!-- catalogue:start -->" not in text:
        raise RuntimeError(f"markers missing in {path}")
    with open(path, "w") as f:
        f.write(new)


def about(app):
    try:
        text = json.loads(app.get("additionalSettings") or "{}").get("about", "")
    except ValueError:
        text = ""
    return " ".join(text.split()).replace("|", "/")


def write_catalogue(cfg, apps, origin, failed, path):
    by_cat = {}
    for a in apps:
        by_cat.setdefault((a.get("categories") or ["Uncategorized"])[0], []).append(a)
    counts = {}
    for name in origin.values():
        counts[name] = counts.get(name, 0) + 1
    lines = [
        "# Catalogue",
        "",
        f"{len(apps)} apps, generated automatically. Do not edit.",
        "",
        "## Sources (priority order)",
        "",
        "| Source | Type | Apps provided |",
        "|---|---|---|",
    ]
    for src in cfg["sources"]:
        ref = src.get("url") or (
            f"https://github.com/{src['repo']}" if "repo" in src else ""
        )
        lines.append(
            f"| {src['name']} | {src['type']} | {counts.get(src['name'], 0)} |"
            if not ref
            else f"| [{src['name']}]({ref}) | {src['type']} | {counts.get(src['name'], 0)} |"
        )
    for cat in sorted(by_cat):
        lines += [
            "",
            f"## {cat} ({len(by_cat[cat])})",
            "",
            "| App | Description | Source |",
            "|---|---|---|",
        ]
        for a in sorted(by_cat[cat], key=lambda x: x["name"].lower()):
            lines.append(
                f"| [{a['name'].replace('|', '/')}]({a['url']}) | {about(a)} | {origin[a['id']]} |"
            )
    if failed:
        lines += ["", "## Skipped (no APK in releases)", ""]
        lines += [f"- {u}" for u in sorted(failed)]
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    with open(
        os.environ.get("SOURCES")
        or os.path.join(os.path.dirname(__file__), "sources.yaml")
    ) as f:
        cfg = yaml.safe_load(f)
    seen_url, seen_id, merged, report, failed = set(), set(), [], [], set()
    origin = {}
    for src in cfg["sources"]:
        t, added = src["type"], 0
        if t == "repos":
            cands = [(u, src.get("category", "")) for u in src["urls"]]
            entries = [(None, u, c) for u, c in cands]
        elif t == "link-page":
            entries = [
                (None, u, c)
                for u, c in repos_from_page(fetch_file(src), src.get("category", ""))
            ]
        else:
            if t == "github-release-asset":
                rel = json.loads(
                    get(f"https://api.github.com/repos/{src['repo']}/releases/latest")
                )
                asset = next(
                    a for a in rel["assets"] if re.search(src["asset_regex"], a["name"])
                )
                text = get(asset["browser_download_url"])
            else:
                text = fetch_file(src)
            apps = (
                apps_from_deeplinks(text)
                if t == "deeplink-page"
                else apps_from_json(text)
            )
            entries = [(a, a.get("url", ""), None) for a in apps]
        for app, url, cat in entries:
            key = norm(url)
            if key in seen_url or key in failed or (app and app.get("id") in seen_id):
                continue
            if app is None:
                if not REPO_RE.match(url):
                    continue
                app = build_entry(url, cat, report)
                if app is None:
                    failed.add(key)
                    continue
            seen_url.add(key)
            seen_id.add(app["id"])
            merged.append(app)
            origin[app["id"]] = src["name"]
            added += 1
        print(f"{src['name']}: +{added}", file=sys.stderr)
    for line in report:
        print(line, file=sys.stderr)
    out = os.environ.get("OUTPUT", "obtainium-thor-pack.json")
    with open(out, "w") as f:
        json.dump({"apps": merged}, f, indent=2, ensure_ascii=False)
    print(f"total: {len(merged)} -> {out}", file=sys.stderr)
    write_readme_section(merged, os.environ.get("README", "README.md"))
    write_catalogue(
        cfg, merged, origin, failed, os.environ.get("CATALOGUE", "CATALOGUE.md")
    )


if __name__ == "__main__":
    main()
