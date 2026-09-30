from app.pii import scrub_text


def test_scrub_email() -> None:
    out = scrub_text("Email me at student@vinuni.edu.vn")
    assert "student@" not in out
    assert "REDACTED_EMAIL" in out


def test_scrub_common_vietnamese_phone_formats() -> None:
    phone_numbers = (
        "0901234567",
        "090 123 4567",
        "090.123.4567",
        "090-123-4567",
        "+84 90 123 4567",
    )

    for phone_number in phone_numbers:
        out = scrub_text(f"Contact: {phone_number}")
        assert phone_number not in out
        assert "REDACTED_PHONE_VN" in out


def test_scrub_cccd() -> None:
    out = scrub_text("CCCD của tôi là 079203001234")
    assert "079203001234" not in out
    assert "REDACTED_CCCD" in out


def test_scrub_credit_card_formats() -> None:
    for card in ("4111 1111 1111 1111", "4111-1111-1111-1111", "4111111111111111"):
        out = scrub_text(f"Card: {card}")
        assert card not in out
        assert "REDACTED_CREDIT_CARD" in out


def test_card_starting_with_zero_is_not_split_into_phone() -> None:
    out = scrub_text("Card 0123 4567 8901 2345 end")
    assert out == "Card [REDACTED_CREDIT_CARD] end"


def test_scrub_passport_vn() -> None:
    out = scrub_text("Passport C1234567")
    assert "C1234567" not in out
    assert "REDACTED_PASSPORT_VN" in out


def test_non_pii_text_is_unchanged() -> None:
    text = "How do I debug tail latency for req-1a2b3c4d?"
    assert scrub_text(text) == text
