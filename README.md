# Rank contacts by closeness

A terminal tool that ranks people from an Apple Contacts vCard export. You sort them into four buckets, then answer pairwise questions about who you are closer to. Scores use a Glicko-style update with a floor for each bucket, and the result is saved locally in `data.json`.

## Quick start

Python 3.9 or newer. The standard library is enough. There is no `requirements.txt`.

```bash
git clone https://github.com/amahjoor/contact-closeness-ranker.git
cd contact-closeness-ranker
python main.py
```

Export a vCard from Apple Contacts: Select All, then File > Export > Export vCard. The import prompt defaults to `~/Desktop/contacts.vcf`.

## Commands

`python main.py` opens a menu:

- `i` import contacts from a `.vcf` file. A later import adds new names only.
- `b` assign a bucket. `1` close, `2` casual, `3` acquaintance, `4` peripheral, `s` skip, `q` stop.
- `c` compare a pair. `1` left person, `2` right person, `e` equal, `s` skip, `q` stop.
- `v` view the ranking.
- `r` change one contact's bucket.
- `s` show stats.
- `q` save and quit.

State is written to `data.json` next to `main.py`. That file is gitignored. It holds names, phone numbers, and emails from the vCard.

Buckets seed a score and a floor on a 0–1000 scale:

| Bucket | Seed | Floor |
| --- | --- | --- |
| Close | 875 | 750 |
| Casual | 625 | 500 |
| Acquaintance | 375 | 250 |
| Peripheral | 125 | 0 |

The next pair is chosen from bucketed contacts with high uncertainty and similar scores. Pairs already compared are skipped.

## Requirements

- Python 3.9+
- A `.vcf` export. The parser reads `FN` (or `N`), the first `TEL`, the first `EMAIL`, and `ORG`. Entries with none of those are skipped.

## Tests

```bash
python test_smoke.py
```

The smoke test uses `test_contacts.vcf` in this folder. It does not read your address book. `test_data.json` is deleted at the end of the run.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Bug reports and pull requests are welcome.

## License

[MIT](LICENSE)
