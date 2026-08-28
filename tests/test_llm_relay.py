"""Reaching the model provider from a network it refuses to talk to.

openrouter.ai answers 403 «Access denied by security policy» to the Yandex Cloud
function the daily job runs in — the balance endpoint and the completions
endpoint alike, verified from inside. The same Vercel relay that already carries
the Telegram reports carries these calls too, and it holds the API key, so the
cloud function is deployed without one and cannot spend money directly."""

import os

import llm


class Recorder(object):
    """Stands in for requests: remembers the call, answers with a canned body."""

    def __init__(self, status=200, body=None):
        self.status, self.body, self.calls = status, body or {}, []

    def __call__(self, url, headers=None, data=None, timeout=None):
        self.calls.append(dict(url=url, headers=headers or {}, data=data))
        return self

    @property
    def status_code(self):
        return self.status

    def json(self):
        return self.body

    @property
    def text(self):
        return str(self.body)


def env(**values):
    """Set exactly these relay-related variables, clearing the rest."""
    keys = ('OPENROUTER_API_KEY', 'RELAY_URL', 'RELAY_SECRET',
            'OPENROUTER_RELAY_URL', 'PREFER_RELAY')
    saved = {k: os.environ.get(k) for k in keys}
    for k in keys:
        os.environ.pop(k, None)
    os.environ.update({k: v for k, v in values.items() if v})
    return saved


def restore(saved):
    for k, v in saved.items():
        os.environ.pop(k, None)
        if v is not None:
            os.environ[k] = v


# --- where the calls are addressed ------------------------------------------

def test_the_openrouter_endpoint_is_derived_from_the_telegram_one():
    """One address to configure. The two endpoints live in the same relay."""
    saved = env(RELAY_URL='https://my-relay.example/api/notify')
    try:
        assert llm.relay_endpoint() == 'https://my-relay.example/api/openrouter'
    finally:
        restore(saved)


def test_an_explicit_address_wins_over_the_derived_one():
    saved = env(RELAY_URL='https://a.example/api/notify',
                OPENROUTER_RELAY_URL='https://b.example/hook')
    try:
        assert llm.relay_endpoint() == 'https://b.example/hook'
    finally:
        restore(saved)


# --- which mode the client ends up in ---------------------------------------

def test_with_no_key_but_a_relay_the_client_goes_through_the_relay():
    """This is the cloud function: deployed without a key on purpose."""
    saved = env(RELAY_URL='https://relay.example/api/notify', RELAY_SECRET='s3cret')
    try:
        client, reason = llm.open_client({'text_generation': {'min_balance_usd': 0}})
        assert reason == ''
        assert client.relay == 'https://relay.example/api/openrouter'
    finally:
        restore(saved)


def test_with_a_key_of_its_own_the_client_calls_the_provider_directly():
    """This is a laptop: no reason to add a hop, and the relay's quota is not
    spent on work that can go straight out."""
    saved = env(OPENROUTER_API_KEY='sk-test', RELAY_URL='https://relay.example/api/notify',
                RELAY_SECRET='s3cret')
    try:
        client, _ = llm.open_client({'text_generation': {'min_balance_usd': 0}})
        assert client.relay == ''
    finally:
        restore(saved)


def test_neither_a_key_nor_a_relay_switches_generation_off():
    saved = env()
    try:
        client, reason = llm.open_client({})
        assert client is None
        assert 'ретранслятор' in reason
    finally:
        restore(saved)


# --- what actually goes over the wire ---------------------------------------

def test_a_relayed_call_carries_the_secret_and_never_the_key():
    recorder = Recorder(body={'choices': [{'message': {'content': 'Да'}}],
                              'usage': {'cost': 0.000005}})
    client = llm.Client('', llm.settings({}), relay='https://relay.example/api/openrouter',
                        relay_secret='s3cret')
    original, llm.requests.post = llm.requests.post, recorder
    try:
        answer = client.chat([{'role': 'user', 'content': 'привет'}])
    finally:
        llm.requests.post = original

    assert answer == 'Да'
    sent = recorder.calls[0]
    assert sent['url'] == 'https://relay.example/api/openrouter'
    assert sent['headers']['x-relay-secret'] == 's3cret'
    assert 'Authorization' not in sent['headers']
    assert client.spent == 0.000005


def test_the_relay_passes_the_providers_refusal_through_unchanged():
    """The relay returns the upstream status and body untouched, so the retry
    rules — which statuses are worth another attempt — keep working."""
    recorder = Recorder(status=402, body={'error': {'message': 'no credit'}})
    client = llm.Client('', llm.settings({}), relay='https://relay.example/api/openrouter',
                        relay_secret='s3cret')
    original, llm.requests.post = llm.requests.post, recorder
    try:
        try:
            client.chat([{'role': 'user', 'content': 'привет'}])
            raised = None
        except RuntimeError as exc:
            raised = str(exc)
    finally:
        llm.requests.post = original

    assert raised and '402' in raised and 'no credit' in raised
    assert len(recorder.calls) == 1          # a fatal status is not retried
