"""The controls docs/COMPLIANCE.md claims, enforced.

A compliance document that nothing checks is a promise. Each test here
is one row of that document: if the console starts calling a third-party
host, sets a cookie, stores something that is not a setting, stops saying
who wrote a claim, or fails the accessibility audit, the build goes red
and the document is wrong until someone fixes the code or the claim.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONSOLE = ROOT / "docs" / "index.html"
FEED = ROOT / "docs" / "feed.json"


@pytest.fixture(scope="module")
def page() -> str:
    return CONSOLE.read_text()


@pytest.fixture(scope="module")
def feed() -> dict:
    if not FEED.exists():  # pragma: no cover
        pytest.skip("docs/feed.json not built")
    return json.loads(FEED.read_text())


# ---------------------------------------------------- privacy: data flows

# Everything the page may ask for, all same-origin. The two api/ routes
# exist only behind the local server; on the static site they are not
# called (speech) or never reached (tts without a key).
ALLOWED_REQUESTS = {"feed.json", "api/speech", "api/tts", "audio/crowd.mp3",
                    "audio/roar.mp3", "audio/swell.mp3",
                    "fonts/archivo-latin-wdth-normal.woff2",
                    "fonts/archivo-latin-ext-wdth-normal.woff2"}


def test_no_third_party_hosts(page):
    """No analytics, no CDN, no font service: a viewer's IP address goes
    to whoever serves the page and to nobody else."""
    # Two kinds of URL in the page are not requests and are excluded:
    # link-preview tags (read by a chat app or social site when someone
    # shares the link, never fetched by the page) and an SVG namespace
    # identifier inside the favicon, which is a name, not an address.
    scanned = re.sub(r'<meta property="og:[^>]*>', "", page)
    scanned = scanned.replace("xmlns='http://www.w3.org/2000/svg'", "")
    hosts = re.findall(r"""["'(]\s*(?:https?:)?//([a-z0-9.-]+)""", scanned, re.I)
    assert not hosts, f"the console references external hosts: {sorted(set(hosts))}"


def test_every_request_is_on_the_list(page):
    literal = set(re.findall(r"fetch\('([^']+)'", page))
    literal |= set(re.findall(r"load\('([^']+)'\)", page))
    literal |= set(re.findall(r"url\(([^)$]+)\)", page))
    assert literal <= ALLOWED_REQUESTS, literal - ALLOWED_REQUESTS
    assert {"feed.json", "api/speech", "api/tts"} <= literal


def test_link_previews_point_only_at_this_site(page):
    for url in re.findall(r'<meta property="og:(?:image|url)" content="([^"]+)"', page):
        assert url.startswith("https://hectar-glitches.github.io/gegenpress/"), url


def test_no_cookies(page):
    assert "document.cookie" not in page


def test_browser_storage_holds_settings_and_nothing_else(page):
    """Two keys. The settings object's fields are all preferences -- no
    identifier, no history -- and the Call it score lives in session
    storage, gone when the tab closes."""
    local = set(re.findall(r"localStorage\.(?:get|set)Item\('([^']+)'", page))
    session = re.findall(r"sessionStorage\.(?:get|set)Item\((\w+)\(\)", page)
    assert local == {"gp.acc"}, local
    assert set(session) == {"callKey"}, session
    assert re.search(r"const callKey = \(\) => `gp\.call\.", page)
    m = re.search(r"const ACC_DEF = (\{.*?\});", page, re.S)
    fields = set(re.findall(r"(\w+):", m.group(1)))
    assert fields == {"ad", "voice", "rate", "captions", "large", "motion", "callit"}, fields
    m = re.search(r"let CALL = (\{.*?\}), OPENER", page)
    assert set(re.findall(r"(\w+):", m.group(1))) == {"ans", "missed", "hits", "total", "streak"}


def test_the_speech_key_never_reaches_the_page(page):
    assert "AZURE_SPEECH_KEY" not in page and "Ocp-Apim" not in page


# ------------------------------------------ AI transparency (AI Act Art. 50)

def test_every_claim_says_who_wrote_it(feed):
    for m in feed["moments"]:
        assert m.get("model"), m["player"]
        assert isinstance(m.get("fell_back"), bool) and isinstance(m.get("grounded"), bool)


def test_the_disclosure_exists_in_every_language(feed, page):
    for lang, ui in feed["i18n"]["ui"].items():
        for k in ("wr_template", "wr_model", "wr_fallback"):
            assert ui.get(k), (lang, k)
        assert "{model}" in ui["wr_model"], lang
    assert "$('#lWriter').textContent = writerLabel(m)" in page


# ---------------------------------------------- accessibility (EAA, WCAG AA)

def _axe_available() -> bool:
    if shutil.which("node") is None:
        return False
    probe = subprocess.run(["node", "-e", "require.resolve('axe-core/axe.min.js');require('playwright')"],
                           capture_output=True, env=os.environ)
    return probe.returncode == 0


# CI's accessibility job sets GEGENPRESS_REQUIRE_AXE, so there a missing
# tool is a failure rather than a skip and the claim cannot pass by default.
@pytest.mark.skipif(not _axe_available() and not os.environ.get("GEGENPRESS_REQUIRE_AXE"),
                    reason="axe-core and playwright not installed")
def test_axe_finds_no_wcag_aa_violations():
    """Six states a fan actually sees, WCAG 2.x A/AA rules. An automated
    pass is a floor, not a certificate -- see COMPLIANCE.md."""
    r = subprocess.run(["node", str(ROOT / "scripts" / "a11y_audit.cjs")],
                       capture_output=True, text=True, timeout=240)
    states = json.loads(r.stdout)
    bad = {s["state"]: [v["id"] for v in s["violations"]] for s in states if s["violations"]}
    assert not bad, bad
    assert len(states) == 6


def test_access_services_are_under_the_viewers_control(page):
    """EAA: access services delivered in sync, with the user in control of
    how they are displayed and used."""
    for control in ("ad", "voice", "rate", "captions", "large", "motion"):
        assert f"row('{control}'" in page, control
    assert "caption(it.text);" in page          # captions show the line as it is spoken
    assert 'aria-live' in page and 'role="img"' in page


# ------------------------------------------- enforced by the browser itself

def _csp(page: str) -> dict[str, str]:
    m = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', page)
    assert m, "no Content-Security-Policy on the page"
    return {d.split()[0]: " ".join(d.split()[1:]) for d in m.group(1).split("; ")}


def test_the_browser_blocks_any_third_party(page):
    """The privacy promise does not rest on tests catching a bad edit: a
    script or request to another origin is refused at runtime."""
    csp = _csp(page)
    assert csp["default-src"] == "'self'"
    assert csp["connect-src"] == "'self'"
    assert "http" not in " ".join(csp.values())
    assert csp["object-src"] == "'none'" and csp["form-action"] == "'none'"
    assert '<meta name="referrer" content="no-referrer">' in page


# ------------------------------------------------- hosted: Entra ID sign-in

def test_the_hosted_console_requires_sign_in(page):
    """Written for Azure Static Web Apps, validated here, not deployed (no
    subscription). Every route needs an authenticated user; sign-in is
    Entra ID for one tenant; other providers are switched off; the
    response headers carry the same CSP as the page."""
    cfg = json.loads((ROOT / "docs" / "staticwebapp.config.json").read_text())
    routes = cfg["routes"]
    assert routes[-1] == {"route": "/*", "allowedRoles": ["authenticated"]}
    assert all(r.get("allowedRoles") == ["authenticated"] or r.get("statusCode") == 404 for r in routes)
    assert cfg["responseOverrides"]["401"]["redirect"].startswith("/.auth/login/aad")
    reg = cfg["auth"]["identityProviders"]["azureActiveDirectory"]["registration"]
    assert reg["openIdIssuer"].startswith("https://login.microsoftonline.com/")
    # Names of app settings, never the values: no secret lives in the repo.
    assert set(reg) == {"openIdIssuer", "clientIdSettingName", "clientSecretSettingName"}
    header = cfg["globalHeaders"]["Content-Security-Policy"]
    meta = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', page).group(1)
    assert header == meta + "; frame-ancestors 'none'"


# ------------------------------------------------- retention and records

def test_retention_is_set_and_erasure_is_two_step():
    kql = (ROOT / "kql" / "03_retention.kql").read_text()
    assert ".alter-merge table Events policy retention softdelete = 730d" in kql
    assert "verificationtoken" in kql and "noregrets" not in kql
    assert "03_retention" not in (ROOT / "kql" / "01_schema.kql").read_text()


def test_the_paperwork_exists_and_points_at_real_code():
    for doc in ("docs/privacy/ROPA.md", "docs/privacy/DPIA.md", "docs/A11Y_TESTING.md", "docs/COMPLIANCE.md"):
        text = (ROOT / doc).read_text()
        for link in re.findall(r"\]\(((?!https?:|mailto:|#)[^)#\s]+)", text):
            target = (ROOT / doc).parent / link
            assert target.exists(), f"{doc} links to missing {link}"
