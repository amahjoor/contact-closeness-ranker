"""JSON persistence layer.

Saves and loads the entire app state to a JSON file so sessions
can be resumed across terminal runs.
"""

import json
import os
from dataclasses import asdict
from typing import Dict, List, Set, Tuple

from models import Contact, ContactState, Comparison, Bucket

DEFAULT_SAVE_PATH = os.path.join(os.path.dirname(__file__), "data.json")


def _bucket_to_str(bucket: Bucket) -> str:
    return bucket.value


def _str_to_bucket(s: str) -> Bucket:
    return Bucket(s)


class AppState:
    """Full application state that can be saved/loaded."""

    def __init__(self):
        self.contacts: Dict[str, Contact] = {}          # id -> Contact
        self.states: Dict[str, ContactState] = {}        # contact_id -> ContactState
        self.comparisons: List[Comparison] = []
        self.past_pairs: Set[Tuple[str, str]] = set()    # sorted (id_a, id_b)

    def add_contact(self, contact: Contact) -> ContactState:
        """Add a contact and create its initial state."""
        self.contacts[contact.id] = contact
        state = ContactState(contact_id=contact.id)
        self.states[contact.id] = state
        return state

    def record_comparison(self, comp: Comparison) -> None:
        """Record a completed comparison."""
        self.comparisons.append(comp)
        ids = sorted([comp.contact_a_id, comp.contact_b_id])
        self.past_pairs.add((ids[0], ids[1]))

    def get_contact(self, contact_id: str) -> Contact:
        return self.contacts[contact_id]

    def get_state(self, contact_id: str) -> ContactState:
        return self.states[contact_id]

    def all_states(self) -> List[ContactState]:
        return list(self.states.values())

    def bucketed_states(self) -> List[ContactState]:
        return [s for s in self.states.values() if s.bucket != Bucket.UNASSIGNED]

    def unbucketed_states(self) -> List[ContactState]:
        return [s for s in self.states.values() if s.bucket == Bucket.UNASSIGNED]


def save(app: AppState, path: str = DEFAULT_SAVE_PATH) -> None:
    """Save app state to JSON."""
    data = {
        "contacts": {cid: asdict(c) for cid, c in app.contacts.items()},
        "states": {},
        "comparisons": [asdict(c) for c in app.comparisons],
        "past_pairs": [list(p) for p in app.past_pairs],
    }

    # Serialize states with bucket as string
    for cid, state in app.states.items():
        d = asdict(state)
        d["bucket"] = _bucket_to_str(state.bucket)
        data["states"][cid] = d

    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def load(path: str = DEFAULT_SAVE_PATH) -> AppState:
    """Load app state from JSON. Returns empty state if file doesn't exist."""
    app = AppState()

    if not os.path.exists(path):
        return app

    with open(path, 'r') as f:
        data = json.load(f)

    # Restore contacts
    for cid, cdata in data.get("contacts", {}).items():
        app.contacts[cid] = Contact(**cdata)

    # Restore states
    for cid, sdata in data.get("states", {}).items():
        sdata["bucket"] = _str_to_bucket(sdata["bucket"])
        app.states[cid] = ContactState(**sdata)

    # Restore comparisons
    for cdata in data.get("comparisons", []):
        app.comparisons.append(Comparison(**cdata))

    # Restore past pairs
    for pair in data.get("past_pairs", []):
        app.past_pairs.add(tuple(sorted(pair)))

    return app
