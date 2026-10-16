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
