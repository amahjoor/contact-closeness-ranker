#!/usr/bin/env python3
"""Terminal-based MVP for relationship ranking.

A Glicko-style scoring system that ranks your contacts by closeness
using bucket seeding + adaptive pairwise comparisons.

Usage:
    python3 main.py

First run: import your Apple Contacts .vcf export, bucket everyone,
then do pairwise comparisons. State is saved between sessions.
"""

import os
import sys
from typing import Optional

from models import Contact, ContactState, Comparison, Bucket, BUCKET_CONFIG
from scoring import update_scores, apply_time_decay
from importer import parse_vcf
from selector import select_pair
from storage import AppState, save, load, DEFAULT_SAVE_PATH


# ── Terminal helpers ──────────────────────────────────────────────────────

def clear():
    os.system('cls' if os.name == 'nt' else 'clear')


def header(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


def prompt(msg: str, valid: str = "") -> str:
    """Get user input. If valid is set, keep asking until input is in valid chars."""
    while True:
        try:
            val = input(f"  {msg} ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 'q'
        if not valid or val in valid:
            return val
        print(f"    Invalid input. Options: {valid}")


# ── Import ────────────────────────────────────────────────────────────────

def do_import(app: AppState) -> None:
    header("IMPORT CONTACTS")

    if app.contacts:
        print(f"  You already have {len(app.contacts)} contacts loaded.")
        choice = prompt("Re-import will add new contacts only. Continue? (y/n)", "yn")
        if choice != 'y':
            return

    default_path = os.path.expanduser("~/Desktop/contacts.vcf")
    print(f"  Export your contacts from Apple Contacts app:")
    print(f"    1. Open Contacts > Select All (Cmd+A)")
    print(f"    2. File > Export > Export vCard...")
    print(f"    3. Save to Desktop as contacts.vcf")
    print()

    path = input(f"  Path to .vcf file [{default_path}]: ").strip()
    if not path:
        path = default_path

    path = os.path.expanduser(path)

    if not os.path.exists(path):
        print(f"\n  File not found: {path}")
        return

    contacts = parse_vcf(path)
    print(f"\n  Parsed {len(contacts)} contacts from file.")

    # Deduplicate against existing contacts by name
    existing_names = {c.name.lower() for c in app.contacts.values() if c.name}
    new_count = 0
    for contact in contacts:
        if contact.name and contact.name.lower() in existing_names:
            continue
        app.add_contact(contact)
        existing_names.add(contact.name.lower() if contact.name else "")
        new_count += 1

    print(f"  Added {new_count} new contacts ({len(app.contacts)} total).")
    save(app)


# ── Bucket Assignment ─────────────────────────────────────────────────────

def do_bucket(app: AppState) -> None:
    header("BUCKET ASSIGNMENT")

    unbucketed = app.unbucketed_states()
    if not unbucketed:
        print("  All contacts are already bucketed.")
        return

    total = len(unbucketed)
    print(f"  {total} contacts need bucketing.\n")
    print("  For each person, type:")
    print("    1 = Close        (best friends, family, inner circle)")
    print("    2 = Casual       (friends you hang out with regularly)")
    print("    3 = Acquaintance (christmas card people, rarely interact)")
    print("    4 = Peripheral   (know of each other, not really friends)")
    print("    s = Skip (come back later)")
    print("    q = Quit bucketing\n")

    done = 0
    for i, state in enumerate(unbucketed):
        contact = app.get_contact(state.contact_id)
        name = contact.display_name()
        extra = ""
        if contact.organization:
            extra = f" ({contact.organization})"

        remaining = total - i
        print(f"  [{remaining} left] {name}{extra}")
        choice = prompt("[1] Close  [2] Casual  [3] Acquaintance  [4] Peripheral  [s]kip  [q]uit:", "1234sq")

        if choice == 'q':
            break
        elif choice == 's':
            continue
        elif choice == '1':
            state.apply_bucket(Bucket.CLOSE)
            done += 1
        elif choice == '2':
            state.apply_bucket(Bucket.CASUAL)
            done += 1
        elif choice == '3':
            state.apply_bucket(Bucket.ACQUAINTANCE)
            done += 1
        elif choice == '4':
            state.apply_bucket(Bucket.PERIPHERAL)
            done += 1

        # Save periodically
        if done % 20 == 0 and done > 0:
            save(app)

    save(app)
    print(f"\n  Bucketed {done} contacts this session.")

    # Show distribution
    _show_bucket_distribution(app)


def _show_bucket_distribution(app: AppState):
    counts = {b: 0 for b in Bucket}
    for state in app.all_states():
        counts[state.bucket] += 1

    print(f"\n  Distribution:")
    print(f"    Close:        {counts[Bucket.CLOSE]}")
    print(f"    Casual:       {counts[Bucket.CASUAL]}")
    print(f"    Acquaintance: {counts[Bucket.ACQUAINTANCE]}")
    print(f"    Peripheral:   {counts[Bucket.PERIPHERAL]}")
    print(f"    Unassigned:   {counts[Bucket.UNASSIGNED]}")


# ── Pairwise Comparison ──────────────────────────────────────────────────

def do_compare(app: AppState) -> None:
    header("PAIRWISE COMPARISON")

    bucketed = app.bucketed_states()
    if len(bucketed) < 2:
        print("  Need at least 2 bucketed contacts. Run bucketing first.")
        return

    print(f"  {len(bucketed)} contacts ready for comparison.")
    print(f"  {len(app.comparisons)} comparisons done so far.\n")
    print("  For each pair, who are you CLOSER to?")
    print("    1 = Left person")
    print("    2 = Right person")
    print("    e = Equal (about the same closeness)")
    print("    s = Skip (can't decide / don't want to)")
    print("    q = Quit comparing\n")

    done = 0
    while True:
        pair = select_pair(bucketed, app.past_pairs)
        if pair is None:
            print("  No more informative pairs to compare right now.")
            break

        state_a, state_b = pair
        contact_a = app.get_contact(state_a.contact_id)
        contact_b = app.get_contact(state_b.contact_id)

        name_a = contact_a.display_name()
        name_b = contact_b.display_name()

        # Show score context in debug-friendly way
        rd_a = f"(RD:{state_a.rd:.0f})" if state_a.rd > 100 else ""
        rd_b = f"(RD:{state_b.rd:.0f})" if state_b.rd > 100 else ""

        print(f"\n  #{done + 1}:  [1] {name_a}  {rd_a}")
        print(f"         vs")
        print(f"        [2] {name_b}  {rd_b}")

        choice = prompt("[1] Left  [2] Right  [e]qual  [s]kip  [q]uit:", "12esq")

        if choice == 'q':
            break
        elif choice == 's':
            continue
        elif choice == '1':
            # A is closer
            update_scores(state_a, state_b, is_draw=False)
            comp = Comparison(
                contact_a_id=state_a.contact_id,
                contact_b_id=state_b.contact_id,
                winner_id=state_a.contact_id,
            )
            app.record_comparison(comp)
            done += 1
        elif choice == '2':
            # B is closer
            update_scores(state_b, state_a, is_draw=False)
            comp = Comparison(
                contact_a_id=state_a.contact_id,
                contact_b_id=state_b.contact_id,
                winner_id=state_b.contact_id,
            )
            app.record_comparison(comp)
            done += 1
        elif choice == 'e':
            # Equal
            update_scores(state_a, state_b, is_draw=True)
            comp = Comparison(
                contact_a_id=state_a.contact_id,
                contact_b_id=state_b.contact_id,
                winner_id=None,
            )
            app.record_comparison(comp)
            done += 1

        # Save every 5 comparisons
        if done % 5 == 0 and done > 0:
            save(app)

    save(app)
    print(f"\n  Completed {done} comparisons this session ({len(app.comparisons)} total).")


# ── View Rankings ─────────────────────────────────────────────────────────

def do_view(app: AppState) -> None:
    header("RANKINGS")

    bucketed = app.bucketed_states()
    if not bucketed:
        print("  No bucketed contacts yet. Run bucketing first.")
        return

    # Apply time decay to all contacts before displaying
    for state in bucketed:
        apply_time_decay(state)

    # Sort by score descending
    bucketed.sort(key=lambda s: s.score, reverse=True)

    print(f"  {'#':<4} {'Name':<30} {'Score':<8} {'RD':<6} {'Bucket':<12} {'Comps':<6}")
    print(f"  {'-'*4} {'-'*30} {'-'*8} {'-'*6} {'-'*12} {'-'*6}")

    for i, state in enumerate(bucketed, 1):
        contact = app.get_contact(state.contact_id)
        name = contact.display_name()[:30]
        bucket_label = state.bucket.value.capitalize()
        confidence = ""
        if state.rd > 150:
            confidence = " ?"  # uncertain
        elif state.rd < 50:
            confidence = " *"  # very confident

        print(f"  {i:<4} {name:<30} {state.score:<8.1f} {state.rd:<6.0f} {bucket_label:<12} {state.comparison_count:<6}{confidence}")

    print(f"\n  Legend: * = high confidence, ? = uncertain (needs more comparisons)")
    print(f"  Total: {len(bucketed)} ranked, {len(app.unbucketed_states())} unassigned")

    # Show by bucket
    choice = prompt("\nFilter by bucket? [c]lose [a]casual [q]acquaintance [p]eripheral [n]o:", "caqpn")
    if choice == 'n':
        return

    bucket_map = {'c': Bucket.CLOSE, 'a': Bucket.CASUAL, 'q': Bucket.ACQUAINTANCE, 'p': Bucket.PERIPHERAL}
    if choice in bucket_map:
        filtered = [s for s in bucketed if s.bucket == bucket_map[choice]]
        filtered.sort(key=lambda s: s.score, reverse=True)
        label = bucket_map[choice].value.capitalize()
        print(f"\n  {label} contacts ({len(filtered)}):")
        print(f"  {'#':<4} {'Name':<30} {'Score':<8} {'RD':<6} {'Comps':<6}")
        print(f"  {'-'*4} {'-'*30} {'-'*8} {'-'*6} {'-'*6}")
        for i, state in enumerate(filtered, 1):
            contact = app.get_contact(state.contact_id)
            name = contact.display_name()[:30]
            print(f"  {i:<4} {name:<30} {state.score:<8.1f} {state.rd:<6.0f} {state.comparison_count:<6}")


# ── Rebucket ──────────────────────────────────────────────────────────────

def do_rebucket(app: AppState) -> None:
    header("REBUCKET A CONTACT")

    print("  Search for a contact to change their bucket.")
    query = input("  Name (partial match): ").strip().lower()

    if not query:
        return

    matches = []
    for contact in app.contacts.values():
        if query in contact.display_name().lower():
            matches.append(contact)

    if not matches:
        print("  No matches found.")
        return

    print(f"\n  Found {len(matches)} match(es):")
    for i, contact in enumerate(matches[:20], 1):
        state = app.get_state(contact.id)
        print(f"    {i}. {contact.display_name()} [{state.bucket.value}, score={state.score:.0f}]")

    if len(matches) == 1:
        idx = 0
    else:
        try:
            num = int(input("\n  Select number: ").strip())
            idx = num - 1
        except (ValueError, IndexError):
            print("  Invalid selection.")
            return

    if idx < 0 or idx >= len(matches):
        print("  Invalid selection.")
        return

    contact = matches[idx]
    state = app.get_state(contact.id)

    print(f"\n  {contact.display_name()}")
    print(f"  Current: {state.bucket.value} (score={state.score:.0f}, RD={state.rd:.0f})")
    print()

    choice = prompt("[1] Close  [2] Casual  [3] Acquaintance  [4] Peripheral  [x] Remove from ranking  [c]ancel:", "1234xc")

    if choice == 'c':
        return
    elif choice == 'x':
        state.bucket = Bucket.UNASSIGNED
        state.score = 500.0
        state.rd = 350.0
        state.comparison_count = 0
        state.last_compared_at = None
        print(f"  Removed {contact.display_name()} from ranking.")
    else:
        bucket_map = {'1': Bucket.CLOSE, '2': Bucket.CASUAL, '3': Bucket.ACQUAINTANCE, '4': Bucket.PERIPHERAL}
        new_bucket = bucket_map[choice]
        old_bucket = state.bucket

        # Re-seeding: set new bucket score but keep some memory of pairwise
        # by blending old score with new seed. Reset RD to high since
        # the relationship has fundamentally changed.
        state.bucket = new_bucket
        new_seed = BUCKET_CONFIG[new_bucket]["seed"]
        if state.comparison_count > 0:
            # Blend: 70% new seed, 30% old score
            state.score = new_seed * 0.7 + state.score * 0.3
        else:
            state.score = new_seed
        state.score = max(BUCKET_CONFIG[new_bucket]["floor"], state.score)
        state.rd = 200.0  # Reset uncertainty - needs recalibration

        print(f"  Moved {contact.display_name()} from {old_bucket.value} to {new_bucket.value}.")
        print(f"  New score: {state.score:.0f} (will refine with comparisons)")

    save(app)


# ── Stats ─────────────────────────────────────────────────────────────────

def do_stats(app: AppState) -> None:
    header("STATS")

    total = len(app.contacts)
    bucketed = len(app.bucketed_states())
    comparisons = len(app.comparisons)

    print(f"  Contacts:    {total}")
    print(f"  Bucketed:    {bucketed}")
    print(f"  Comparisons: {comparisons}")
    print(f"  Unique pairs compared: {len(app.past_pairs)}")

    if bucketed > 0:
        avg_comps = sum(s.comparison_count for s in app.bucketed_states()) / bucketed
        avg_rd = sum(s.rd for s in app.bucketed_states()) / bucketed
        print(f"  Avg comparisons per contact: {avg_comps:.1f}")
        print(f"  Avg uncertainty (RD): {avg_rd:.0f}")

        # Confidence breakdown
        confident = sum(1 for s in app.bucketed_states() if s.rd < 80)
        uncertain = sum(1 for s in app.bucketed_states() if s.rd > 150)
        mid = bucketed - confident - uncertain
        print(f"\n  Confidence: {confident} solid, {mid} moderate, {uncertain} uncertain")

    _show_bucket_distribution(app)


# ── Main Menu ─────────────────────────────────────────────────────────────

def main():
    app = load()

    while True:
        clear()
        header("RELATIONSHIP RANKER")

        total = len(app.contacts)
        bucketed = len(app.bucketed_states())
        unbucketed = len(app.unbucketed_states())
        comparisons = len(app.comparisons)

        if total == 0:
            print("  No contacts loaded. Start by importing your contacts.\n")
        else:
            print(f"  {total} contacts | {bucketed} bucketed | {comparisons} comparisons\n")

        print("  [i] Import contacts from .vcf file")
        print("  [b] Bucket contacts (close / casual / acquaintance / peripheral)")
        print("  [c] Compare (pairwise ranking)")
        print("  [v] View rankings")
        print("  [r] Rebucket a contact")
        print("  [s] Stats")
        print("  [q] Quit")
        print()

        choice = prompt("What do you want to do?", "ibcvrsq")

        if choice == 'q':
            save(app)
            print("  Saved. Bye.")
            break
        elif choice == 'i':
            do_import(app)
        elif choice == 'b':
            do_bucket(app)
        elif choice == 'c':
            do_compare(app)
        elif choice == 'v':
            do_view(app)
        elif choice == 'r':
            do_rebucket(app)
        elif choice == 's':
            do_stats(app)

        if choice != 'q':
            prompt("Press Enter to continue...", "")


if __name__ == "__main__":
    main()
