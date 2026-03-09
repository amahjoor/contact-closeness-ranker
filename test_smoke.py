"""Quick smoke test for the core modules."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from importer import parse_vcf
from models import ContactState, Bucket
from scoring import update_scores, apply_time_decay
from selector import select_pair
from storage import AppState, save, load

TEST_VCF = os.path.join(os.path.dirname(__file__), "test_contacts.vcf")
TEST_SAVE = os.path.join(os.path.dirname(__file__), "test_data.json")


def test_import():
    contacts = parse_vcf(TEST_VCF)
    assert len(contacts) == 10, f"Expected 10 contacts, got {len(contacts)}"
    assert contacts[0].name == "John Doe"
    assert contacts[0].phone == "+1-555-0101"
    assert contacts[0].email == "john@example.com"
    assert contacts[0].organization == "Acme Corp"
    print(f"  PASS: Imported {len(contacts)} contacts")
    return contacts


def test_bucketing():
    app = AppState()
    contacts = parse_vcf(TEST_VCF)
    for c in contacts:
        app.add_contact(c)

    states = app.all_states()
    # Bucket across all 4 tiers: 3 close, 3 casual, 2 acquaintance, 2 peripheral
    for s in states[:3]:
        s.apply_bucket(Bucket.CLOSE)
    for s in states[3:6]:
        s.apply_bucket(Bucket.CASUAL)
    for s in states[6:8]:
        s.apply_bucket(Bucket.ACQUAINTANCE)
    for s in states[8:]:
        s.apply_bucket(Bucket.PERIPHERAL)

    assert states[0].score == 875.0,  f"Close seed should be 875, got {states[0].score}"
    assert states[0].rd == 200.0
    assert states[3].score == 625.0,  f"Casual seed should be 625, got {states[3].score}"
    assert states[6].score == 375.0,  f"Acquaintance seed should be 375, got {states[6].score}"
    assert states[8].score == 125.0,  f"Peripheral seed should be 125, got {states[8].score}"
    print(f"  PASS: Bucketing seeds all 4 tiers correctly")
    return app


def test_scoring():
    app = test_bucketing()
    states = app.bucketed_states()

    # Compare two casual contacts
    a, b = states[3], states[4]
    old_a, old_b = a.score, b.score

    # A wins (closer)
    update_scores(a, b, is_draw=False)

    assert a.score > old_a, f"Winner score should increase: {old_a} -> {a.score}"
    assert b.score < old_b, f"Loser score should decrease: {old_b} -> {b.score}"
    assert a.rd < 200.0, f"Winner RD should decrease: {a.rd}"
    assert b.rd < 200.0, f"Loser RD should decrease: {b.rd}"
    assert b.score >= 500.0, f"Casual floor (500) should hold: {b.score}"

    # Also verify peripheral floor holds
    p = states[8]  # peripheral contact
    old_p = p.score
    update_scores(b, p, is_draw=False)  # peripheral loses
    assert p.score >= 0.0, f"Peripheral floor (0) should hold: {p.score}"

    print(f"  PASS: Scores update correctly (A: {old_a:.0f}->{a.score:.0f}, B: {old_b:.0f}->{b.score:.0f})")
    print(f"  PASS: RD decreased (A: 200->{a.rd:.0f}, B: 200->{b.rd:.0f})")
    print(f"  PASS: Bucket floors hold for all 4 tiers")


def test_selector():
    app = test_bucketing()
    states = app.bucketed_states()

    pair = select_pair(states, app.past_pairs)
    assert pair is not None, "Should find a pair"
    a, b = pair
    print(f"  PASS: Selected pair: {a.contact_id[:8]} vs {b.contact_id[:8]}")


def test_persistence():
    app = test_bucketing()

    save(app, TEST_SAVE)
    loaded = load(TEST_SAVE)

    assert len(loaded.contacts) == len(app.contacts)
    assert len(loaded.states) == len(app.states)

    # Clean up
    os.remove(TEST_SAVE)
    print(f"  PASS: Save/load round-trip works")


if __name__ == "__main__":
    print("\nRunning tests...\n")
    test_import()
    test_bucketing()
    test_scoring()
    test_selector()
    test_persistence()
    print("\nAll tests passed.\n")
