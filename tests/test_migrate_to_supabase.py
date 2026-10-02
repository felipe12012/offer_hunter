import migrate_to_supabase


class FakeMirror:
    def __init__(self, counts, imported=None, sent=2):
        self._counts = counts
        self._imported = imported or {"products": 3, "points": 5}
        self._sent = sent

    def import_history(self, history):
        return self._imported

    def import_seen(self, keys):
        return self._sent

    def count(self, table):
        return self._counts[table]


def test_migration_is_verified_when_the_database_holds_at_least_what_was_imported():
    mirror = FakeMirror({"offer_products": 3, "offer_price_points": 9, "offer_sent": 2})
    assert migrate_to_supabase.migrate(mirror, {}, []) is True


def test_migration_fails_loudly_when_rows_are_missing(capsys):
    mirror = FakeMirror({"offer_products": 2, "offer_price_points": 5, "offer_sent": 2})
    assert migrate_to_supabase.migrate(mirror, {}, []) is False
    assert "INCOMPLETE" in capsys.readouterr().out


def test_main_exits_with_error_when_supabase_is_not_configured(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    assert migrate_to_supabase.main() == 1
