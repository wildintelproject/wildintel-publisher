# Camtrap DP example

A small, synthetic Camtrap DP package — 2 deployments, 5 media files (one
private), 5 observations — for trying out `wildintel-publisher` without a
live Trapper server. The images are generated placeholders (simple drawn
scenes), not real photographs; the observations/species are made up.

```
.
├── datapackage.json
├── deployments.csv
├── media.csv             ← media m5 is filePublic=false (a "human" observation)
├── observations.csv
└── images/                ← 5 local .jpg files, referenced by media.csv's filePath
```

Validated against the real Camtrap DP 1.0.2 schema (`product generate-metadata`
runs frictionless validation over the network — see
[services/common.py's `validate_camtrap_dp`](../../wildintel_publisher/services/common.py)).

## Try it

```bash
wildintel-publisher product generate-metadata \
  --input-dir examples/camtrapdp --product-type camtrapdp

wildintel-publisher hfh prepare \
  --input-dir examples/camtrapdp --output-dir /tmp/camtrapdp-hfh-out --link-images
```

**Use `--link-images`, not the default `--mirror-images`.** `media.csv`'s
`filePath` here is a local relative path (`images/cam1_....jpg`), not a live
URL — real Trapper downloads always use a signed HTTP(S) URL there, which is
what `--mirror-images` actually downloads from (see
[docs/product-camtrapdp.md](../../docs/product-camtrapdp.md#filepath-is-a-one-shot-token-url)).
`--link-images` skips that download and just filters `media.csv` down to
public rows, which this offline example supports.

Check the private-media filtering worked: `/tmp/camtrapdp-hfh-out/media.csv`
should have 4 rows (m5 removed), and its matching `observations.csv` should
have 4 rows too (o5 removed along with it).
