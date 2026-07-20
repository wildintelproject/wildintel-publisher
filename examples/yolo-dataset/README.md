# YOLO dataset example

A small, synthetic YOLO object-detection dataset — 3 classes (deer/fox/bird),
4 training images, 2 validation images, 2 test images — for trying out
`wildintel-publisher` without a real dataset on hand. The images are
generated placeholders (simple drawn scenes), not real photographs.

```
.
├── data.yaml
├── images/
│   ├── train/    ← 4 .jpg files
│   ├── val/      ← 2 .jpg files
│   └── test/     ← 2 .jpg files
└── labels/       ← matching YOLO-format .txt files (class cx cy w h, normalized),
    ├── train/      same train/val/test split layout as images/
    ├── val/
    └── test/
```

`labels/` travels alongside `images/` into every publish (mirror mode) — see
[services/yolo_adapter.py](../../wildintel_publisher/services/yolo_adapter.py)'s
`prepare()`.

## Try it

```bash
wildintel-publisher product generate-metadata \
  --input-dir examples/yolo-dataset --product-type yolo

wildintel-publisher hfh prepare \
  --input-dir examples/yolo-dataset --output-dir /tmp/yolo-hfh-out
```

No `--link-images`/`--mirror-images` distinction matters here the way it does
for Camtrap DP — a YOLO dataset's images are already local files, so mirror
mode (the default) just copies `images/` as-is; nothing gets downloaded.
