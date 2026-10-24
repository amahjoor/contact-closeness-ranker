# Contributing

Bugs and pull requests are welcome.

## Run the tests

```bash
python test_smoke.py
```

The fixture is `test_contacts.vcf`. Do not replace it with a real address book.

## What not to commit

- `data.json` and any other file of real contacts
- `*.vcf` exports. `test_contacts.vcf` is the only vCard that belongs in git
- API keys, `.env` files, or phone numbers from your own export

## Pull requests

1. Describe the behavior you changed.
2. Keep the smoke test passing.
3. This project is [MIT](LICENSE). Your contribution is licensed the same way.
