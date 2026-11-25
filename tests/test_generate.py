import io
import json
import runpy
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

import generate

MARKERS = "<!-- catalogue:start -->\n<!-- catalogue:end -->\n"


def release(*names, **flags):
    return {"assets": [{"name": n} for n in names], **flags}


class FakeOpener:
    def __init__(self, *results):
        self.results = list(results)
        self.requests = []

    def open(self, req, timeout):
        self.requests.append(req)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return io.BytesIO(result)


@pytest.mark.parametrize(
    "url", ["file:///etc/hostname", "http://example.invalid/", "ftp://x/y"]
)
def test_opener_refuses_non_https(url):
    with pytest.raises(urllib.error.URLError, match="unknown url type"):
        generate.https_opener().open(url, timeout=1)


def test_get_sends_token_only_to_github_api(monkeypatch):
    fake = FakeOpener(b"a", b"b")
    monkeypatch.setattr(generate, "OPENER", fake)
    monkeypatch.setattr(generate, "TOKEN", "t")
    assert generate.get("https://api.github.com/x", "text/raw") == "a"
    assert generate.get("https://codeberg.org/x") == "b"
    first, second = fake.requests
    assert first.get_header("Authorization") == "Bearer t"
    assert first.get_header("Accept") == "text/raw"
    assert second.get_header("Authorization") is None


def test_get_retries_then_fails(monkeypatch):
    waits = []
    monkeypatch.setattr(generate.time, "sleep", waits.append)
    fake = FakeOpener(OSError("1"), OSError("2"), OSError("3"))
    monkeypatch.setattr(generate, "OPENER", fake)
    with pytest.raises(RuntimeError, match="after 3 attempts"):
        generate.get("https://example.invalid/")
    assert waits == [5, 10]


def test_fetch_file(monkeypatch):
    monkeypatch.setattr(generate, "get", lambda *a: a)
    assert generate.fetch_file({"url": "u"}) == ("u",)
    url, accept = generate.fetch_file({"repo": "o/r", "path": "p"})
    assert url == "https://api.github.com/repos/o/r/contents/p"
    assert accept == "application/vnd.github.raw"


def test_norm_and_api_base():
    assert generate.norm("https://GitHub.com/O/R.git") == "github.com/o/r"
    assert generate.norm("https://Example.org/a/") == "https://example.org/a"
    assert generate.norm(None) == ""
    github = generate.api_base("github.com", "o", "r")
    assert github == "https://api.github.com/repos/o/r"
    codeberg = generate.api_base("codeberg.org", "o", "r")
    assert codeberg == "https://codeberg.org/api/v1/repos/o/r"


def test_parsers():
    assert generate.apps_from_json('[{"id": 1}]') == [{"id": 1}]
    assert generate.apps_from_json('{"apps": []}') == []
    link = urllib.parse.quote('{"id": "a (b)"}', safe="()")
    deeplinks = generate.apps_from_deeplinks(f"[x](obtainium://app/{link})")
    assert deeplinks == [{"id": "a (b)"}]
    page = (
        "https://github.com/o/a\n## Games\n"
        "https://github.com/o/b. https://github.com/o/releases"
    )
    assert generate.repos_from_page(page, "D") == [
        ("https://github.com/o/a", "D"),
        ("https://github.com/o/b", "Games"),
    ]
    escaped = "https:\\u002F\\u002Fgithub.com\\u002Fo\\u002Fc"
    assert generate.repos_from_page(escaped) == [("https://github.com/o/c", "")]


@pytest.mark.parametrize(
    ("releases", "prereleases"),
    [
        ([release("a.apk")], False),
        ([release("a.apk", prerelease=True), release("a.zip")], True),
    ],
)
def test_build_entry(monkeypatch, releases, prereleases):
    monkeypatch.setattr(
        generate, "get", lambda u: json.dumps(releases if "releases" in u else {})
    )
    entry = generate.build_entry("https://github.com/O/R.git", "", [])
    assert (entry["id"], entry["name"], entry["categories"]) == ("o.r", "R", [])
    settings = json.loads(entry["additionalSettings"])
    assert settings["includePrereleases"] is prereleases


def test_build_entry_skips(monkeypatch):
    report = []
    monkeypatch.setattr(generate, "get", lambda u: "[]" if "releases" in u else "{}")
    assert generate.build_entry("https://codeberg.org/o/r", "c", report) is None
    monkeypatch.setattr(generate, "get", lambda u: "not json")
    assert generate.build_entry("https://github.com/o/r", "c", report) is None
    assert len(report) == 2


def test_readme_requires_markers(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("none")
    with pytest.raises(RuntimeError, match="markers missing"):
        generate.write_readme_section([], readme)


def test_about_tolerates_bad_settings():
    assert generate.about({"additionalSettings": "{"}) == ""
    assert generate.about({}) == ""


def prepare_run(monkeypatch, tmp_path, sources):
    config = tmp_path / "sources.yaml"
    config.write_text(json.dumps({"sources": sources}))
    readme = tmp_path / "README.md"
    readme.write_text(MARKERS)
    monkeypatch.setenv("SOURCES", str(config))
    monkeypatch.setenv("README", str(readme))
    monkeypatch.setenv("OUTPUT", str(tmp_path / "out.json"))
    monkeypatch.setenv("CATALOGUE", str(tmp_path / "CATALOGUE.md"))
    return readme


def test_main(monkeypatch, tmp_path):
    def app(ident, url):
        return {"id": ident, "url": url, "name": ident}

    link = urllib.parse.quote(json.dumps(app("d", "https://example.org/d")))
    asset = {"name": "pack.json", "browser_download_url": "https://dl/pack"}
    latest = "https://api.github.com/repos/o/pack/releases/latest"
    responses = {
        latest: json.dumps({"assets": [asset]}),
        "https://dl/pack": json.dumps([app("p", "https://github.com/o/packed")]),
        "https://deeplinks": f"[d](obtainium://app/{link})",
        "https://json": json.dumps([app("p", "https://github.com/o/other")]),
        "https://page": "https://github.com/o/new https://github.com/o/empty",
    }
    for name in ("new", "empty"):
        base = f"https://api.github.com/repos/o/{name}"
        responses[base] = "{}"
        apks = [release("a.apk")] if name == "new" else []
        responses[base + "/releases?per_page=30"] = json.dumps(apks)
    monkeypatch.setattr(generate, "get", lambda url, accept=None: responses[url])
    packed = ["https://github.com/o/packed", "not-a-repo"]
    readme = prepare_run(
        monkeypatch,
        tmp_path,
        [
            {
                "name": "rel",
                "type": "github-release-asset",
                "repo": "o/pack",
                "asset_regex": "pack",
            },
            {"name": "dl", "type": "deeplink-page", "url": "https://deeplinks"},
            {"name": "js", "type": "json-url", "url": "https://json"},
            {"name": "list", "type": "repos", "urls": packed},
            {"name": "page", "type": "link-page", "url": "https://page"},
            {
                "name": "again",
                "type": "repos",
                "urls": ["https://github.com/o/empty"],
            },
        ],
    )
    generate.main()
    published = json.loads((tmp_path / "out.json").read_text())["apps"]
    assert [a["id"] for a in published] == ["p", "d", "o.new"]
    assert "**3 apps**" in readme.read_text()
    assert "- github.com/o/empty" in (tmp_path / "CATALOGUE.md").read_text()


def test_script_entry_point(monkeypatch, tmp_path):
    prepare_run(monkeypatch, tmp_path, [])
    runpy.run_path(str(Path(generate.__file__)), run_name="__main__")
    assert json.loads((tmp_path / "out.json").read_text()) == {"apps": []}
