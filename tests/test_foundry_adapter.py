"""The Foundry adapter, exercised without an Azure subscription.

Only the live call needs a provisioned resource. Everything before it --
the imports, the two constructor call sites, the selection logic, and the
stringification of the response -- runs locally, and that is exactly
where adapter bugs live: a renamed import, a keyword the library stopped
accepting, a response object that stringifies to a repr instead of the
sentence Desk was supposed to write.

This project has been bitten by that once already. `MetricSignal()`, the
KQL half of the ICC gate, had never compiled, and nothing noticed because
nothing ran it. Code that has never run may never have worked. So the
parts of the Foundry path that can be checked on a laptop are checked
here, and the claim in the README is bounded by what these tests prove.
"""

from __future__ import annotations

import inspect

import pytest

from gegenpress.agents import FoundryModel, TemplateModel, get_model

agent_framework = pytest.importorskip(
    "agent_framework", reason="pip install agent-framework azure-identity"
)

ENDPOINT = "https://example.services.ai.azure.com/api/projects/p"
MODEL = "gpt-5-mini"


@pytest.fixture
def foundry_env(monkeypatch):
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", ENDPOINT)
    monkeypatch.setenv("FOUNDRY_MODEL", MODEL)


def test_the_imports_the_adapter_depends_on_still_exist():
    """A renamed module is the cheapest way for this path to rot."""
    from agent_framework import Agent  # noqa: F401
    from agent_framework.foundry import FoundryChatClient  # noqa: F401
    from azure.identity import AzureCliCredential  # noqa: F401


def test_call_sites_match_the_installed_signatures():
    """Bind the arguments the adapter actually passes.

    This fails loudly on an upstream rename instead of at minute nine of
    a ten-minute provisioning run.
    """
    from agent_framework import Agent
    from agent_framework.foundry import FoundryChatClient

    inspect.signature(FoundryChatClient.__init__).bind(
        None, project_endpoint=ENDPOINT, model=MODEL, credential=object()
    )
    inspect.signature(Agent.__init__).bind(
        None, client=object(), name="desk", instructions="…"
    )


def test_from_env_builds_a_client(foundry_env):
    model = FoundryModel.from_env()
    assert model.name == "foundry"
    assert model.model == MODEL
    assert model.endpoint == ENDPOINT


def test_from_env_refuses_to_guess_when_unconfigured(monkeypatch):
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    monkeypatch.delenv("FOUNDRY_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="FOUNDRY_PROJECT_ENDPOINT"):
        FoundryModel.from_env()


def test_get_model_selects_foundry_only_when_configured(foundry_env, monkeypatch):
    assert get_model().name == "foundry"
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT")
    assert get_model().name == "template"


def test_get_model_falls_back_rather_than_raising(foundry_env, monkeypatch):
    """An unreachable Foundry must degrade to templates, not take the
    pipeline down. The Desk sentence gets duller; it never goes missing."""
    def explode(cls):
        raise RuntimeError("no credential")

    monkeypatch.setattr(FoundryModel, "from_env", classmethod(explode))
    assert isinstance(get_model(prefer_foundry=True), TemplateModel)


def test_complete_returns_the_sentence_not_a_repr(foundry_env, monkeypatch):
    """The failure this guards against is silent.

    If the response object stringified to `AgentResponse(messages=[...])`,
    Desk would hand the Gate a repr full of digits, the Gate would reject
    every one, and the pipeline would quietly fall back to templates
    forever while appearing to use the model.
    """
    sentence = "30' Kowalski: pass range 13.8 tonight, against a season norm of 17.1."

    class FakeResponse:
        def __str__(self) -> str:
            return sentence + "\n"

    class FakeAgent:
        def __init__(self, *, client, name, instructions):
            assert name == "desk"
            assert instructions
        async def run(self, user):
            assert user
            return FakeResponse()

    model = FoundryModel.from_env()
    monkeypatch.setattr(model, "_Agent", FakeAgent)
    assert model.complete("system", "user") == sentence


def test_agent_response_stringifies_to_its_text():
    """The real contract behind the test above, checked against the
    installed library rather than assumed."""
    from agent_framework import AgentResponse

    assert "__str__" in AgentResponse.__dict__
    assert "self.text" in inspect.getsource(AgentResponse.__str__)
