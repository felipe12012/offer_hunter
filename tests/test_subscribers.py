import notifier
import subscribers
from subscribers import handle_update, process_updates
from supabase_sync import SupabaseError


class FakeStore:
    def __init__(self, offset=None, fail_on=None):
        self.state = {} if offset is None else {"telegram_update_offset": str(offset)}
        self.upserts = []
        self.deactivated = []
        self.fail_on = fail_on

    def get_bot_state(self, key):
        return self.state.get(key)

    def set_bot_state(self, key, value):
        self.state[key] = value

    def upsert_subscriber(self, chat_id, username, first_name, active):
        if self.fail_on == chat_id:
            raise SupabaseError("down")
        self.upserts.append((chat_id, username, first_name, active))

    def set_subscribers_active(self, chat_ids, active):
        self.deactivated.append((list(chat_ids), active))


def message(update_id, text, chat_id=10, chat_type="private", first_name="Ana"):
    return {
        "update_id": update_id,
        "message": {
            "text": text,
            "chat": {"id": chat_id, "type": chat_type},
            "from": {"username": "ana", "first_name": first_name},
        },
    }


def install(monkeypatch, updates):
    sent = []

    def fake_call(token, method, **payload):
        if method == "getUpdates":
            fake_call.last_payload = payload
            return {"ok": True, "result": updates}
        sent.append((method, payload))
        return {"ok": True}

    monkeypatch.setattr(subscribers, "_call", fake_call)
    return sent, fake_call


def test_start_registers_the_subscriber_and_welcomes_them(monkeypatch):
    sent, _ = install(monkeypatch, [message(5, "/start")])
    store = FakeStore()

    counts = process_updates(store, token="tok")

    assert counts == {"subscribed": 1, "unsubscribed": 0}
    assert store.upserts == [(10, "ana", "Ana", True)]
    assert sent[0][0] == "sendMessage" and sent[0][1]["chat_id"] == 10 and "Ana" in sent[0][1]["text"]
    assert store.state["telegram_update_offset"] == "6"


def test_start_with_bot_suffix_and_payload_is_still_start(monkeypatch):
    install(monkeypatch, [])
    store = FakeStore()
    assert handle_update(message(1, "/start@CazaOfertasBot hola"), store, "tok") == "subscribed"


def test_stop_deactivates_the_subscriber(monkeypatch):
    install(monkeypatch, [message(7, "/stop")])
    store = FakeStore()
    counts = process_updates(store, token="tok")
    assert counts["unsubscribed"] == 1
    assert store.deactivated == [([10], False)]


def test_blocking_the_bot_deactivates_the_subscriber(monkeypatch):
    update = {"update_id": 3, "my_chat_member": {"chat": {"id": 10, "type": "private"},
                                                  "new_chat_member": {"status": "kicked"}}}
    install(monkeypatch, [update])
    store = FakeStore()
    assert process_updates(store, token="tok")["unsubscribed"] == 1
    assert store.deactivated == [([10], False)]


def test_groups_and_plain_text_are_ignored(monkeypatch):
    sent, _ = install(monkeypatch, [message(1, "/start", chat_type="group"), message(2, "hola")])
    store = FakeStore()
    assert process_updates(store, token="tok") == {"subscribed": 0, "unsubscribed": 0}
    assert store.upserts == [] and sent == []
    assert store.state["telegram_update_offset"] == "3"


def test_help_answers_without_registering(monkeypatch):
    sent, _ = install(monkeypatch, [message(1, "/ayuda")])
    store = FakeStore()
    process_updates(store, token="tok")
    assert store.upserts == [] and len(sent) == 1


def test_resumes_from_the_saved_offset(monkeypatch):
    _, call = install(monkeypatch, [])
    process_updates(FakeStore(offset=42), token="tok")
    assert call.last_payload["offset"] == 42


def test_storage_failure_keeps_the_update_for_the_next_run(monkeypatch):
    install(monkeypatch, [message(1, "/start", chat_id=11), message(2, "/start", chat_id=12)])
    store = FakeStore(fail_on=12)
    counts = process_updates(store, token="tok")
    assert counts["subscribed"] == 1
    assert store.state["telegram_update_offset"] == "2"  # update 2 is fetched again next run


def test_malformed_update_is_skipped_not_retried_forever(monkeypatch):
    install(monkeypatch, [{"update_id": 1, "message": {"text": "/start", "chat": {"type": "private"}}}])
    store = FakeStore()
    process_updates(store, token="tok")
    assert store.state["telegram_update_offset"] == "2"


def test_never_raises_when_telegram_is_down(monkeypatch):
    monkeypatch.setattr(subscribers, "_call", lambda *a, **k: None)
    store = FakeStore()
    assert process_updates(store, token="tok") == {"subscribed": 0, "unsubscribed": 0}


def test_without_a_token_it_does_nothing(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert process_updates(FakeStore()) == {"subscribed": 0, "unsubscribed": 0}


def test_unreachable_set_is_exposed_by_notifier():
    assert isinstance(notifier.UNREACHABLE_CHATS, set)
