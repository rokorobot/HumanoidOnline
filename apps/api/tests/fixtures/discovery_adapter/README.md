# Discovery adapter fixtures (SYNTHETIC)

Every page here is **invented** for offline tests of the Slice B adapter
pipeline (docs/16 §12.1). "Example Robotics" and every model (EX-Alpha 7,
EX-Beta 2, ...) are fictional; `maker.example` is a reserved example domain.
No value here describes a real product or company, and none may be copied into
the catalogue.

`__MAKER__` is replaced by each test with a unique manufacturer name, so that
tests never collide with other candidates in the shared test database.

- `v1/` - first observation of the site.
- `v2/` - the same site one run later: a price change, a spec change, a
  preorder, a removed page (404) and an unchanged announcement.

`site.json` maps each URL to a file (relative to its directory) or to
`{"status": N}`.
