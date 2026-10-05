"""Sending the same offer to several chats must not repeat the slow part: one upload, then the photo's file_id;
a host whose URLs Telegram cannot fetch is not tried again; the whole stage has a time budget."""
import pytest

import main_fast
import notifier
from notifier import send_offers
from tests.test_notifier import FakeResponse, make_scored

PHOTO_ANSWER = {"ok": True, "result": {"photo": [{"file_id": "small"}, {"file_id": "BIG"}]}}


class Telegram:
    """requests.post stand-in: URL photos fail for `bad_hosts`, uploads and file_ids work and return a file_id."""

    def __init__(self, bad_hosts=()):
        self.bad_hosts = bad_hosts
        self.calls = []

    def __call__(self, url, json=None, data=None, files=None, timeout=None):
        method = url.rsplit("/", 1)[-1]
        body = json if json is not None else data
        self.calls.append((method, body, files))
        if method == "sendPhoto" and json is not None:
            photo = json["photo"]
            if photo.startswith("http") and any(host in photo for host in self.bad_hosts):
                return FakeResponse(400, payload={"description": "Bad Request: failed to get HTTP URL content"})
        return FakeResponse(200, payload=PHOTO_ANSWER if method == "sendPhoto" else {"ok": True})

    def kinds(self):
        out = []
        for method, body, files in self.calls:
            if method != "sendPhoto":
                out.append(method)
            elif files is not None:
                out.append("upload")
            elif body["photo"].startswith("http"):
                out.append("url")
            else:
                out.append("file_id")
        return out


@pytest.fixture
def telegram(monkeypatch):
    for name in ("TELEGRAM_ALERT_CHAT_ID", "TELEGRAM_ALERT_THREAD_ID", "TELEGRAM_PUBLIC_CHAT_ID"):
        monkeypatch.delenv(name, raising=False)
    fake = Telegram()
    monkeypatch.setattr("notifier.requests.post", fake)
    monkeypatch.setattr("notifier.requests.get", lambda url, **kw: FakeResponse(200, content=b"jpeg-bytes"))
    monkeypatch.setattr("notifier.time.sleep", lambda s: None)
    return fake


def test_the_second_chat_gets_the_photo_by_file_id(telegram):
    send_offers([make_scored("sodimac:1")], bot_token="t", chat_id="MAIN", public_chat_id="PUBLIC",
                subscriber_chat_ids=[111, 222])

    # first send: Telegram fetches the URL (and answers with the file_id); everyone else reuses it
    assert telegram.kinds() == ["url", "file_id", "file_id", "file_id"]
    assert [c[1]["photo"] for c in telegram.calls[1:]] == ["BIG", "BIG", "BIG"]  # the largest size


def test_when_the_url_fails_the_image_is_uploaded_once_and_then_reused(monkeypatch, telegram):
    telegram.bad_hosts = ("img.example",)

    send_offers([make_scored("sodimac:1")], bot_token="t", chat_id="MAIN", public_chat_id="PUBLIC",
                subscriber_chat_ids=[111])

    assert telegram.kinds() == ["url", "upload", "file_id", "file_id"]  # not url+upload for every destination


def test_a_host_that_keeps_failing_is_not_tried_by_url_again(monkeypatch, telegram):
    telegram.bad_hosts = ("img.example",)
    offers = [make_scored(f"sodimac:{i}", store=f"s{i}", category=f"c{i}", image_url=f"https://img.example/{i}.jpg")
              for i in range(5)]

    send_offers(offers, bot_token="t", chat_id="MAIN")

    kinds = telegram.kinds()
    assert kinds.count("url") == notifier.URL_FAILURES_BEFORE_SKIP  # then it goes straight to the upload
    assert kinds.count("upload") == 5


def test_a_failure_of_one_host_does_not_affect_another(telegram):
    telegram.bad_hosts = ("bad.example",)
    bad = [make_scored(f"sodimac:{i}", store=f"s{i}", category=f"c{i}", image_url=f"https://bad.example/{i}.jpg")
           for i in range(4)]
    good = make_scored("falabella:9", store="falabella", category="x", image_url="https://good.example/9.jpg")

    send_offers([*bad, good], bot_token="t", chat_id="MAIN")

    good_calls = [c for c in telegram.calls if c[1] and "good.example" in str(c[1].get("photo", ""))]
    assert len(good_calls) == 1  # still sent by URL


def test_a_rejected_file_id_falls_back_to_the_url(monkeypatch, telegram):
    notifier._PHOTO_FILE_IDS["https://img.example/p.jpg"] = "STALE"
    original = telegram.__call__

    def reject_ids(url, json=None, data=None, files=None, timeout=None):
        if json and json.get("photo") == "STALE":
            telegram.calls.append(("sendPhoto", json, None))
            return FakeResponse(400, payload={"description": "wrong file identifier"})
        return original(url, json=json, data=data, files=files, timeout=timeout)

    monkeypatch.setattr("notifier.requests.post", reject_ids)
    sent = send_offers([make_scored("sodimac:1")], bot_token="t", chat_id="MAIN")
    assert len(sent) == 1


def test_the_stage_stops_at_its_time_budget_and_leaves_the_rest_for_the_next_run(monkeypatch, telegram):
    clock = {"now": 0.0}
    monkeypatch.setattr("notifier.time.monotonic", lambda: clock["now"])
    real_sleep = lambda s: clock.__setitem__("now", clock["now"] + 200)   # each message "takes" 200 s
    monkeypatch.setattr("notifier.time.sleep", real_sleep)
    offers = [make_scored(f"sodimac:{i}", store=f"s{i}", category=f"c{i}") for i in range(10)]

    sent = send_offers(offers, bot_token="t", chat_id="MAIN")

    assert 1 < len(sent) < 10  # budget 420 s at 200 s per message: a handful, not all
    assert len(sent) == 4


def test_without_a_budget_problem_everything_is_sent(telegram):
    offers = [make_scored(f"sodimac:{i}", store=f"s{i}", category=f"c{i}") for i in range(10)]
    assert len(send_offers(offers, bot_token="t", chat_id="MAIN")) == 10


# ---- recorded at once, not at the end of a long run ----------------------------------------------------

def test_delivered_offers_are_recorded_in_supabase_right_away(monkeypatch):
    recorded = []

    class FakeStore:
        def record_sent(self, offers):
            recorded.extend(offers)

    monkeypatch.setattr(main_fast.SupabaseSync, "from_env", classmethod(lambda cls: FakeStore()))
    main_fast.record_delivered([make_scored("sodimac:1")])
    assert [o.deal.id for o in recorded] == ["sodimac:1"]


def test_recording_nothing_or_failing_never_stops_the_run(monkeypatch):
    class Broken:
        def record_sent(self, offers):
            raise RuntimeError("supabase down")

    monkeypatch.setattr(main_fast.SupabaseSync, "from_env", classmethod(lambda cls: Broken()))
    main_fast.record_delivered([make_scored("sodimac:1")])   # logged, not raised
    main_fast.record_delivered([])                           # nothing to do
