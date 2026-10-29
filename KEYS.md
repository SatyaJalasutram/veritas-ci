# Veritas evidence signing keys

The SHA-256 fingerprints of the public keys that sign Veritas evidence, by
key id. A report's signature is trusted only if its key's fingerprint is
listed here: `docs/verify-a-report.md` in the Veritas repository has the
20-line check, which reads this file.

This file is attached to every release of this repository as it is
created (releases are immutable: an attached KEYS.md is never replaced),
and changes only through a reviewed pull request by the Veritas owner,
outside the Veritas service, so a compromised service can't vouch for a
key of its own.

A key is added by the key ceremony: generated inside OpenBao as
non-exportable, its fingerprint read from OpenBao directly (the command
below, run by the owner), and added here by pull request.

Each line is `` - `<key id>`: `sha256:<64 hex>` (<deployment>, since <date>) ``.
A key id names the deployment and the version: `production-v1`,
`staging-v1`. An id is listed once. A staging line ends with
"staging: never used for customer evidence"; Veritas's verify script
accepts a staging key only with `--staging`, and a production key by
default.
The fingerprint is SHA-256 over the raw 32-byte Ed25519 public key, taken
from the key service itself, never from Veritas:

```sh
bao read -format=json transit/keys/veritas-evidence \
  | python3 -c 'import base64,hashlib,json,sys; k=json.load(sys.stdin)["data"]["keys"]
for v in sorted(k, key=int): print(f"<deployment>-v{v}", "sha256:" + hashlib.sha256(base64.b64decode(k[v]["public_key"])).hexdigest())'
```

A key is never removed from this file: reports it signed stay checkable.

## Keys

   - `staging-v1`: `sha256:dc5a5628f2a6630701f08eebeb5372dfe81f5e5f86fab08a8af6d8a1e8d9252a` (staging, since 2026-10-29; staging: never used for customer evidence)
