# Rules and regulations

Which rules a broadcaster or league deploying Gegenpress would be held to,
what each one asks, what this project does about it, and the test that
fails the build if that stops being true.

The last column is the point. A compliance page that nothing checks is a
promise; every row marked **enforced** here is a test in [`tests/`](../tests)
that runs on every push. Where a rule is only partly met, or not met at
all, it says so in the same table rather than in a footnote.

*This maps engineering controls to the rules. It is not legal advice, and
whether a given deployment falls inside each rule is for that deployer's
counsel to decide.*

## The matrix

| Rule | What it asks | What Gegenpress does | Evidence |
| --- | --- | --- | --- |
| **EU AI Act, Art. 50: transparency.** Applies from 2 Aug 2026. Art. 50(2) machine-readable marking has a grace period to 2 Dec 2026 for systems already on the market. | Tell people when content is AI-generated (Art. 50(4) covers AI text published to inform the public, and relaxes the duty where a human holds editorial responsibility). Mark generated output in a machine-readable way. | **Disclosure.** Every claim on the strap says who wrote it, and who approved it, in five languages. **Editorial responsibility.** A model-written sentence is a draft until a named producer approves it (`python -m gegenpress review approve <id> --by "Name"`). Until then the template airs. Decisions go to an append-only log, and a draft edited by even one character needs a new approval. **Machine-readable marking.** Each claim in the feed carries `provenance`: `generated_by` (ai or template), writer, human-review status, and SHA-256 fingerprints of the brief and the text. `python -m gegenpress verify-feed` recomputes them and catches any edit made after the gate. | **Enforced:** [`test_editorial.py`](../tests/test_editorial.py) (9), [`test_privacy.py`](../tests/test_privacy.py) provenance (4), [`test_compliance.py`](../tests/test_compliance.py) disclosure (2) |
| **GDPR / UK GDPR, Art. 5(1)(d): accuracy.** Performance data is personal data, which FIFPRO's Charter of Player Data Rights also says. | Personal data must be accurate. | No claim reaches air with a number the data does not support. The gate checks every digit against the brief it was built from, and falls back to a template when a model gets one wrong. Gate precision, claim integrity and refusal correctness are all 100% across 373 claims and three seeds. | **Enforced:** `python -m gegenpress eval` exits non-zero below 100% ([CI](../.github/workflows/ci.yml)); [`test_browser_gate.py`](../tests/test_browser_gate.py) |
| **GDPR, Art. 5(1)(a): fairness** | Processing must not be unjustifiably detrimental to the person. | The ICC gate refuses personal claims on metrics with no between-player signal. Recovery time (ICC 0.006) measures the match, not the man, so *"slow for him"* is a sentence this system will not produce about anyone. A player is not judged on noise. | **Enforced:** [`test_match_level_metrics_are_refused_a_personal_claim`](../tests/test_form.py), [`test_why_refuses_a_personal_claim_on_an_ungated_metric`](../tests/test_agents.py), refusal correctness in `eval` |
| **GDPR, Art. 5(1)(c) and Art. 25: minimisation, privacy by design** | Collect no more than needed; build privacy in by default. | The console needs no account and sends nothing about the viewer anywhere. It loads only same-origin files. It sets no cookies and runs no analytics, CDN or third-party fonts. It sends no referrer. The Azure voice, when used, sends the line being spoken and nothing else, and the server keeps the key. | **Enforced twice.** By the browser: a Content-Security-Policy limits the page to its own origin, so an added tracker is blocked at runtime ([`test_the_browser_blocks_any_third_party`](../tests/test_compliance.py)). By tests: [`test_no_third_party_hosts`, `test_every_request_is_on_the_list`, `test_no_cookies`, `test_the_speech_key_never_reaches_the_page`](../tests/test_compliance.py) |
| **ePrivacy Directive, Art. 5(3): terminal equipment.** EDPB Guidelines 2/2023 ¶44 list local storage, and say the rule applies when that information is *accessed*. | Consent before storing or reading information on the user's device, unless strictly necessary for a service they asked for. | Two browser-storage entries, both settings the viewer chose: accessibility preferences, and the Call it score for this tab (gone when the tab closes). Neither leaves the device. The Access panel says so in all five languages. | **Enforced:** [`test_browser_storage_holds_settings_and_nothing_else`](../tests/test_compliance.py) checks that the stored fields are preferences and nothing else |
| **European Accessibility Act.** In force since 28 Jun 2025. It covers the websites and apps of services giving access to audiovisual media. | Accessible website or app. Access services such as audio description and subtitles delivered in high quality, synchronised with sound and video, with the user in control of how they appear. | Audio description of the whole match, at key-moment or full-commentary detail, in five languages. Three outputs: a neural voice, the browser voice (Microsoft's Natural voices in Edge), or the viewer's own screen reader through a live region. Captions show each line as it is spoken. Speed, captions, larger text and reduce motion are under the viewer's control. Every number the describer can say comes from the event, the score or the clock. | **Enforced:** [`test_access_services_are_under_the_viewers_control`](../tests/test_compliance.py), [`test_every_spoken_number_comes_from_the_data`](../tests/test_audio_description.py) |
| **WCAG 2.2 AA** (EN 301 549, the harmonised standard, incorporates WCAG 2.1 AA) | Perceivable, operable, understandable, robust. | axe-core, WCAG 2.0, 2.1 and 2.2 A/AA rules, run across six states a fan actually sees: the opening frame, the Access panel, a Call it question, the Try it panel, fan mode, and Arabic with larger text. **0 violations in all six.** The first run found 40 contrast failures and an unlabelled input. The fixes went in with the audit. Keyboard throughout: Space plays, ↑/↓ answer Call it, Escape closes panels. | **Enforced:** a dedicated CI job installs axe-core and Chromium and runs [`scripts/a11y_audit.cjs`](../scripts/a11y_audit.cjs) and [`test_axe_finds_no_wcag_aa_violations`](../tests/test_compliance.py). There, a missing tool is a failure, not a skip |
| **GDPR / UK GDPR, Art. 15 and 20: access and portability.** FIFPRO's Charter asks the same. | A player can get his data, in a structured, machine-readable format he can take elsewhere. | `python -m gegenpress export --player "<name>"`, or the `export_player_data` MCP tool. One JSON document (`gegenpress-player-data/1`) holding every event that names him, his season norm per metric, and *whether each metric may carry a personal claim about him, and why*. It also holds every claim made about him on air, verbatim, with who wrote it and the gate's verdict. Simulator internals and other players' data are excluded, and the document says so. | **Enforced:** [`test_privacy.py`](../tests/test_privacy.py) (5) |
| **GDPR, Art. 21: objection** | A player can object, and processing for that purpose stops unless there are overriding grounds. | Add his id to `data/optout.json`. He is never again the subject of a personal claim, on the strap or in the follow list, and no model sees a brief about him. His slot goes to the next player. An unreadable list stops the build rather than failing open. | **Enforced:** [`test_privacy.py`](../tests/test_privacy.py) (2) |
| **GDPR, Art. 5(1)(e) and Art. 17: storage limitation, erasure** | Keep data no longer than the purpose needs; erase on a valid request. | Two seasons, the minimum the Form Line needs (`softdelete = 730d`). Erasure is ADX's two-step purge: the first step counts, the second deletes. Then the baselines are rebuilt. | Written in [`kql/03_retention.kql`](../kql/03_retention.kql) and checked by [`test_retention_is_set_and_erasure_is_two_step`](../tests/test_compliance.py). **Not applied**: the free cluster rejects policy and purge commands |
| **GDPR, Art. 30 and 35: records, impact assessment** | A record of processing; a DPIA where the processing is high-risk. | A filled-in [record of processing](privacy/ROPA.md) and a [DPIA draft](privacy/DPIA.md) with seven risks. Each measure links to its code and test, and each residual risk is rated. Both are drafts for a DPO; the legal conclusions are left blank on purpose. | Links checked by [`test_the_paperwork_exists_and_points_at_real_code`](../tests/test_compliance.py) |
| **Access control** | Only authorised staff reach the console, the review queue and the data. | Event store: Azure AD / Entra ID. Hosted console: an Azure Static Web Apps config ([`staticwebapp.config.json`](staticwebapp.config.json)). It requires sign-in on every route, uses Entra ID for one tenant, disables other providers, and sends security headers (the same CSP, HSTS, `frame-ancestors 'none'`, `nosniff`). The repo holds only app-setting names, never secrets. | Validated by [`test_the_hosted_console_requires_sign_in`](../tests/test_compliance.py). **Not deployed**: no Azure subscription |
| **Data residency** | Data stays in the region the deployer chose. | Match state and grounding run as KQL inside Azure Data Explorer in the deployer's region. Every language is computed in the feed, so nothing goes to a translation service. | [`test_i18n.py`](../tests/test_i18n.py); [`adx.py`](../src/gegenpress/adx.py) |
| **Operational resilience** | Defined behaviour when a dependency fails. | ADX fails over per call, Foundry falls back to templates, and a bad model sentence is rejected and replaced. `python -m gegenpress chaos` breaks each one and shows the numbers do not move. | **Enforced:** [`test_resilience.py`](../tests/test_resilience.py); chaos runs inside the container in CI |

## What an automated pass does not prove

axe-core catches a subset of WCAG failures. It cannot judge whether a
caption is useful, whether a spoken line is intelligible at 1.25×, or
whether the order of the description makes sense to someone who cannot see
the pitch. That needs blind and partially sighted fans. The
[session plan](A11Y_TESTING.md) is written: who to recruit, seven tasks
with pass marks, and what changes on which result. **It has not been
run.** The pitch itself is a canvas; to assistive technology it is one
labelled image, and the audio description is how its contents reach a
screen reader.

## What is left, and why

Everything an engineer can build for these rules is built and tested
above. What remains needs a person, a contract or a subscription:

- **Decisions for counsel and the DPO.** The legitimate-interests balancing
  test, whether top speed counts as health-adjacent data, and signing off
  the [DPIA](privacy/DPIA.md).
- **A data licence.** Real Premier League event data is licensed
  (Stats Perform/Opta). Everything here is synthetic.
- **An Azure subscription**, to deploy the sign-in config and apply the
  retention policy. Both are written and tested against their own shape;
  neither has run against Azure.
- **The blind and partially sighted fan sessions** in
  [`A11Y_TESTING.md`](A11Y_TESTING.md).
- **A signing key.** The provenance fingerprints detect an edit; they do
  not prove who made the feed, because anyone who can change the text can
  recompute a hash. Signing, or a C2PA manifest, needs a key the deployer
  holds.
