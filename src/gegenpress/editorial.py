"""Producer sign-off: no AI-written sentence goes to air unreviewed.

The gate guarantees a sentence carries no number the data does not
support. It does not make a model's phrasing fit for broadcast, and the EU
AI Act's Article 50(4) disclosure duty for AI-written text is lifted only
where a human holds editorial responsibility for it. So a sentence a model
wrote -- and the gate passed -- is a DRAFT until a named producer approves
it. Until then the deterministic template sentence airs in its place, which
the gate has also passed and which needs no sign-off because no model was
involved.

    python -m gegenpress feed --foundry          # drafts are queued
    python -m gegenpress review                  # what is waiting
    python -m gegenpress review approve <id> --by "J. Producer"
    python -m gegenpress feed --foundry          # approved drafts now air

Decisions go to an append-only log (one JSON object per line), so who
approved what, and when, can be audited after the fact. A draft is
identified by a hash of the sentence itself: change one character and it
is a new draft that needs a new approval.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
from typing import Any

from .agents import DESK_SYSTEM, Segment, TemplateModel

LOG = pathlib.Path(os.environ.get("GEGENPRESS_REVIEW_LOG", "data/review.jsonl"))
DECISIONS = ("approved", "rejected")


def draft_id(seg: Segment, text: str) -> str:
    b = seg.brief
    raw = f"{b.minute}|{b.player_name}|{b.metric_label}|{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def needs_signoff(seg: Segment) -> bool:
    """A model wrote it and the gate passed it. Template sentences, and
    template fallbacks after a model failed the gate, need no sign-off."""
    v = seg.verdict
    return v.model != "template" and v.passed and not v.fell_back


class ReviewLog:
    def __init__(self, path: pathlib.Path | str = LOG) -> None:
        self.path = pathlib.Path(path)

    def entries(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
        return out

    def _append(self, entry: dict[str, Any]) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), **entry}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def state(self) -> dict[str, dict[str, Any]]:
        """Latest status per draft, with the draft's own details."""
        out: dict[str, dict[str, Any]] = {}
        for e in self.entries():
            cur = out.setdefault(e["id"], {})
            cur.update({k: v for k, v in e.items() if k != "event"})
            cur["status"] = "pending" if e["event"] == "submitted" else e["event"]
        return out

    def submit(self, did: str, seg: Segment, text: str) -> None:
        if did in self.state():
            return
        b = seg.brief
        self._append({"event": "submitted", "id": did, "minute": b.minute,
                      "player": b.player_name, "metric": b.metric_label,
                      "writer": seg.verdict.model, "text": text})

    def decide(self, did: str, decision: str, by: str, note: str = "") -> dict[str, Any]:
        if decision not in DECISIONS:
            raise ValueError(f"decision must be one of {DECISIONS}")
        if not by.strip():
            raise ValueError("a decision needs a name: editorial responsibility is a person")
        if did not in self.state():
            raise KeyError(f"no draft {did}")
        return self._append({"event": decision, "id": did, "by": by.strip(), "note": note})

    def pending(self) -> list[dict[str, Any]]:
        return [dict(v, id=k) for k, v in self.state().items() if v["status"] == "pending"]


def apply(seg: Segment, log: ReviewLog) -> dict[str, Any]:
    """Decide what airs for this segment, and say why.

    Mutates seg.verdict.text to the sentence that will air, so everything
    downstream (translations, the gate's allowed numbers, the console)
    sees one text. Returns the review record that ships with the moment.
    """
    if not needs_signoff(seg):
        return {"required": False, "status": "not_required"}
    draft = seg.verdict.text
    did = draft_id(seg, draft)
    log.submit(did, seg, draft)
    st = log.state().get(did, {})
    if st.get("status") == "approved":
        return {"required": True, "status": "approved", "id": did,
                "by": st.get("by"), "at": st.get("at")}
    # Not approved (yet, or at all): the template airs. It passed the same
    # gate and no model wrote it.
    seg.verdict.text = TemplateModel().complete(DESK_SYSTEM, seg.brief.as_prompt())
    return {"required": True, "status": st.get("status", "pending"), "id": did,
            **({"by": st.get("by"), "at": st.get("at")} if st.get("status") == "rejected" else {})}
