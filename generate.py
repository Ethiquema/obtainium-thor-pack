#!/usr/bin/env python3
"""Merge Obtainium packs and generate entries for repositories no pack covers."""
import json, os, re, sys, urllib.parse, urllib.request
import yaml

TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO_RE = re.compile(r"https?://(github\.com|codeberg\.org)/([\w.-]+)/([\w.-]+)", re.I)
NOT_REPOS = {"releases", "issues", "pulls", "wiki", "blob", "tree", "actions"}
SETTINGS_KEYS = {"includePrereleases": False, "fallbackToOlderReleases": True,
                 "filterReleaseTitlesByRegEx": "", "filterReleaseNotesByRegEx": "",
                 "verifyLatestTag": False, "sortMethodChoice": "date",
                 "useLatestAssetDateAsReleaseDate": False, "releaseTitleAsVersion": False,
                 "trackOnly": False, "versionExtractionRegEx": "", "matchGroupToUse": "",
                 "versionDetection": True, "releaseDateAsVersion": False,
                 "useVersionCodeAsOSVersion": False, "apkFilterRegEx": "",
                 "invertAPKFilter": False, "autoApkFilterByArch": True, "appName": "",
                 "appAuthor": "", "shizukuPretendToBeGooglePlay": False,
                 "allowInsecure": False, "exemptFromBackgroundUpdates": False,
                 "skipUpdateNotifications": False, "refreshBeforeDownload": False,
                 "includeZips": False, "zippedApkFilterRegEx": ""}


def get(url, accept=None):
    req = urllib.request.Request(url, headers={"User-Agent": "obtainium-pack-generator"})
    if accept:
        req.add_header("Accept", accept)
    if TOKEN and "api.github.com" in url:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


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


def repos_from_page(text):
    """Repo URLs with the nearest preceding '##' heading as category."""
    out, cat = [], ""
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
    host, owner, repo = m.group(1).lower(), m.group(2), re.sub(r"\.git$", "", m.group(3))
    base = api_base(host, owner, repo)
    try:
        meta = json.loads(get(base))
        rels = json.loads(get(base + "/releases?per_page=30"))
    except Exception as e:
        report.append(f"skipped {url}: {e}")
        return None
    if not any(a["name"].lower().endswith(".apk") for r in rels for a in r.get("assets", [])):
        report.append(f"skipped {url}: no release ships an APK")
        return None
    settings = dict(SETTINGS_KEYS)
    settings["about"] = meta.get("description") or ""
    return {"id": f"{owner}.{repo}".lower(), "url": f"https://{host}/{owner}/{repo}",
            "author": owner, "name": meta.get("name") or repo, "preferredApkIndex": 0,
            "additionalSettings": json.dumps(settings, separators=(",", ":")),
            "categories": [category] if category else [], "allowIdChange": True,
            "overrideSource": "GitHub" if host == "github.com" else "Codeberg"}


def main():
    cfg = yaml.safe_load(open(os.path.join(os.path.dirname(__file__), "sources.yaml")))
    seen_url, seen_id, merged, report, failed = set(), set(), [], [], set()
    for src in cfg["sources"]:
        t, added = src["type"], 0
        if t == "repos":
            cands = [(u, src.get("category", "")) for u in src["urls"]]
            entries = [(None, u, c) for u, c in cands]
        elif t == "link-page":
            entries = [(None, u, c) for u, c in repos_from_page(get(src["url"]))]
        else:
            if t == "github-release-asset":
                rel = json.loads(get(f"https://api.github.com/repos/{src['repo']}/releases/latest"))
                asset = next(a for a in rel["assets"] if re.search(src["asset_regex"], a["name"]))
                text = get(asset["browser_download_url"])
            else:
                text = get(src["url"])
            apps = apps_from_deeplinks(text) if t == "deeplink-page" else apps_from_json(text)
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
            added += 1
        print(f"{src['name']}: +{added}", file=sys.stderr)
    for line in report:
        print(line, file=sys.stderr)
    out = os.environ.get("OUTPUT", "obtainium-thor-pack.json")
    json.dump({"apps": merged}, open(out, "w"), indent=2, ensure_ascii=False)
    print(f"total: {len(merged)} -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
