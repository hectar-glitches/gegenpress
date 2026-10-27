# Record of processing activities (GDPR / UK GDPR Art. 30)

A filled-in record for a broadcaster or league deploying Gegenpress on
real match data. Every answer describes what the code in this repository
does, with a link to it. The bracketed fields are the deployer's to
complete. *Draft for the deployer's data protection officer, not legal
advice.*

| Art. 30(1) | |
| --- | --- |
| **(a) Controller** | [Deploying broadcaster or league, address, DPO contact] |
| **(b) Purposes** | Match commentary and on-screen graphics that compare a player's performance in a live match with his own season, and with the league, during and after the broadcast. Not for player valuation, contract negotiation, selection, betting, or any decision about the player. Use for any of those is a new purpose and needs its own assessment ([DPIA](DPIA.md), risk 4). |
| **(c) Data subjects** | Professional players in the competition. **Viewers are not data subjects of this processing**: the console holds no account, sets no cookie, runs no analytics, and its only browser storage is the viewer's own settings, which never leave the device ([`test_compliance.py`](../../tests/test_compliance.py)). |
| **(c) Categories of personal data** | Match event data naming the player: event type, time, pitch location, outcome, and measurements derived from it (pass length, ball speed, top speed, carry length, recovery time, shot speed, xG). Derived per player: season mean and spread per metric, and the claims made about him on air. No contact, contract, medical, biometric or wearable data. Whether top speed is closer to physical-health data is for counsel; see the [DPIA](DPIA.md), risk 5. |
| **(d) Recipients** | Viewers of the broadcast, who receive the published claims only. Production staff with access to the console and the review queue. Any system calling the MCP server ([`mcp_server.py`](../../src/gegenpress/mcp_server.py)), which must sit behind the deployer's access control in production. |
| **(e) Transfers outside the UK/EEA** | None by design. The event store is Azure Data Explorer in the region the deployer selects. Translations are computed in the pipeline rather than sent to a translation service. The optional Azure AI Speech voice is called in the deployer's chosen region and is sent only the line being spoken. |
| **(f) Retention** | Two seasons, the current one and the last, because the Form Line measures a player against his own recent season. Enforced in ADX by [`kql/03_retention.kql`](../../kql/03_retention.kql) (`softdelete = 730d`). Producer review decisions are kept for the life of the broadcast archive: [deployer to set]. |
| **(g) Security measures** | Azure AD / Entra ID authentication to the event store ([`adx.py`](../../src/gegenpress/adx.py)). Entra ID sign-in in front of the hosted console ([`staticwebapp.config.json`](../staticwebapp.config.json)). A Content-Security-Policy that limits the page to its own origin. A deterministic gate that blocks unsupported numbers. Producer sign-off on any model-written sentence, recorded in an append-only log ([`editorial.py`](../../src/gegenpress/editorial.py)). Per-claim provenance hashes that detect edits after the gate ([`feed.py`](../../src/gegenpress/feed.py)). |

## Data subject rights, and where each is served

| Right | How |
| --- | --- |
| Access (Art. 15), portability (Art. 20) | `python -m gegenpress export --player "<name>"`, or the `export_player_data` MCP tool. Produces one JSON document (`gegenpress-player-data/1`) with every event that names him, his season norms, and every claim made about him on air with who wrote it ([`privacy.py`](../../src/gegenpress/privacy.py)). |
| Rectification (Art. 16) | Correct the event at the source feed and re-ingest. Claims are recomputed from events, so a corrected event corrects every claim built on it. |
| Erasure (Art. 17) | Two-step ADX purge in [`kql/03_retention.kql`](../../kql/03_retention.kql), then rebuild the season baselines. |
| Objection (Art. 21) | Add his player id to `data/optout.json`. From the next feed build he is never the subject of a personal claim, on the strap or in the follow list, and no model ever sees a brief about him. A file that cannot be read stops the build rather than letting him back on air ([`privacy.py`](../../src/gegenpress/privacy.py), [`test_privacy.py`](../../tests/test_privacy.py)). |
