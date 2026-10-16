import database


def test_offer_and_investigation_database_operations(tmp_path) -> None:
    db_path = tmp_path / "test.sqlite3"
    database.initialize_database(db_path)
    analysis = {"facts": {"title": "Test offer"}, "missing_conditions": []}

    offer_id = database.save_offer("Test offer", "10% cashback", analysis, db_path=db_path)
    assert database.get_offer(offer_id, db_path)["analysis"] == analysis
    database.save_offer(
        "Updated offer", "10% cashback up to Rs. 100", analysis,
        status="Active", offer_id=offer_id, db_path=db_path,
    )
    offer = database.get_offer(offer_id, db_path)
    assert offer["title"] == "Updated offer"
    assert offer["status"] == "Active"

    database.save_calculation(600, 60, offer_id, db_path)
    stats = database.get_dashboard_stats(db_path)
    assert stats["saved_offers"] == 1
    assert stats["active_offers"] == 1
    assert stats["estimated_cashback"] == 60

    investigation_id = database.save_investigation(
        {
            "offer_description": "Test offer",
            "merchant": "Shop",
            "transaction_date": "2026-10-16",
            "transaction_amount": "600",
            "expected_cashback": "60",
        },
        db_path=db_path,
    )
    records = database.list_investigations(db_path)
    assert len(records) == 1
    database.save_investigation(
        {
            "offer_description": "Updated offer",
            "merchant": "Shop",
            "transaction_date": "2026-10-16",
            "transaction_amount": "600",
            "expected_cashback": "60",
            "status": "Resolved",
        },
        investigation_id=investigation_id,
        db_path=db_path,
    )
    assert database.list_investigations(db_path)[0]["status"] == "Resolved"
    database.delete_investigation(investigation_id, db_path=db_path, evidence_dir=tmp_path / "evidence")
    database.delete_offer(offer_id, db_path)
    assert database.list_investigations(db_path) == []
    assert database.list_offers(db_path) == []


def test_evidence_deletion_is_confined_to_evidence_folder(tmp_path) -> None:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    inside = evidence_dir / "image.png"
    outside = tmp_path / "outside.png"
    inside.write_bytes(b"inside")
    outside.write_bytes(b"outside")

    database.delete_evidence_file(str(inside), evidence_dir)
    database.delete_evidence_file(str(outside), evidence_dir)

    assert not inside.exists()
    assert outside.exists()


def test_accounts_are_hashed_and_records_are_isolated(tmp_path) -> None:
    db_path = tmp_path / "accounts.sqlite3"
    database.initialize_database(db_path)
    password = "a-long-private-password"
    alice = database.create_user("Alice", password, db_path)
    bob = database.create_user("bob", "another-long-private-password", db_path)
    assert alice == "alice"
    try:
        database.create_user("alice", "a-different-long-password", db_path)
    except ValueError as error:
        assert "already registered" in str(error)
    else:
        raise AssertionError("Duplicate usernames must be rejected.")
    try:
        database.create_user("short", "weak", db_path)
    except ValueError as error:
        assert "12 characters" in str(error)
    else:
        raise AssertionError("Short passwords must be rejected.")
    assert database.verify_user("ALICE", password, db_path) == "alice"
    assert database.verify_user("alice", "wrong-password", db_path) is None

    with database.connect(db_path) as connection:
        stored_hash = connection.execute(
            "SELECT password_hash FROM users WHERE username = ?", (alice,)
        ).fetchone()["password_hash"]
    assert password not in stored_hash

    analysis = {"facts": {"title": "Private offer"}}
    offer_id = database.save_offer(
        "Alice's offer", "10% cashback", analysis, db_path=db_path, owner_id=alice,
    )
    assert len(database.list_offers(owner_id=alice, db_path=db_path)) == 1
    assert database.list_offers(owner_id=bob, db_path=db_path) == []
    assert database.get_offer(offer_id, db_path=db_path, owner_id=bob) is None
    assert database.get_dashboard_stats(db_path=db_path, owner_id=bob)["saved_offers"] == 0
    try:
        database.save_calculation(600, 20, offer_id, db_path, owner_id=bob)
    except ValueError as error:
        assert "not found for this account" in str(error)
    else:
        raise AssertionError("An account must not link a calculation to another user's offer.")

    try:
        database.save_offer(
            "Takeover", "Changed", analysis, offer_id=offer_id,
            db_path=db_path, owner_id=bob,
        )
    except ValueError as error:
        assert "this account" in str(error)
    else:
        raise AssertionError("A second account must not overwrite another user's offer.")

    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    evidence = evidence_dir / "alice.png"
    evidence.write_bytes(b"private")
    investigation_id = database.save_investigation(
        {
            "offer_description": "Private offer",
            "merchant": "Shop",
            "transaction_date": "2026-10-16",
            "transaction_amount": "600",
            "expected_cashback": "20",
            "evidence_path": str(evidence),
        },
        db_path=db_path,
        owner_id=alice,
    )
    database.save_calculation(600, 20, offer_id, db_path, owner_id=alice)
    assert database.list_investigations(owner_id=bob, db_path=db_path) == []
    assert database.get_dashboard_stats(db_path=db_path, owner_id=bob)["estimated_cashback"] == 0
    database.delete_investigation(
        investigation_id, db_path=db_path, evidence_dir=evidence_dir, owner_id=bob,
    )
    assert len(database.list_investigations(owner_id=alice, db_path=db_path)) == 1
    assert database.get_dashboard_stats(db_path=db_path, owner_id=alice)["estimated_cashback"] == 20

    database.delete_user(alice, db_path=db_path, evidence_dir=evidence_dir)
    assert database.list_offers(owner_id=alice, db_path=db_path) == []
    assert database.list_investigations(owner_id=alice, db_path=db_path) == []
    assert not evidence.exists()
    assert database.verify_user(alice, password, db_path) is None
