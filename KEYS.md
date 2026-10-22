# Veritas evidence signing keys

The SHA-256 fingerprints of the public keys that sign Veritas evidence, by
key id. A report's signature is trusted only if its key's fingerprint is
listed here: `docs/verify-a-report.md` in the Veritas repository has the
20-line check, which reads this file.

This file is published with every release of this repository (a release
asset) and changes only through a reviewed pull request by the Veritas
owner, outside the Veritas service, so a compromised service can't vouch
for a key of its own.

Each line is `` - `<key id>`: `sha256:<64 hex>` (<deployment>, since <date>) ``.
The fingerprint is SHA-256 over the raw 32-byte Ed25519 public key, taken
from the key service itself, never from Veritas:

```sh
bao read -format=json transit/keys/veritas-evidence \
  | python3 -c 'import base64,hashlib,json,sys; k=json.load(sys.stdin)["data"]["keys"]
for v in sorted(k, key=int): print(f"openbao-v{v}", "sha256:" + hashlib.sha256(base64.b64decode(k[v]["public_key"])).hexdigest())'
```

A key is never removed from this file: reports it signed stay checkable.

## Keys

No key is listed yet: the first is added after the Phase 1 upgrade, when
staging's key service holds the evidence key.
