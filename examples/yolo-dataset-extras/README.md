# YOLO dataset example with bounding boxes and additional information

A small, synthetic YOLO object-detection dataset that is laid out like a real one
(for instance a camera-trap dataset from a protected area): bounding boxes of 4
animal categories, empty images, full metadata in `data.yaml`, and the extra files
the dataset's authors send along. 14 images — 8 for training, 3 for validation,
3 for testing — with 16 boxes. The images are generated placeholders (coloured
shapes on a drawn scene), not real photographs.

```
.
├── data.yaml                  ← YOLO config + title, description, version, license,
│                                authors (with affiliation), publisher, copyright
│                                holders and extra funding text
├── images/{train,val,test}/   ← .jpg files
├── labels/{train,val,test}/   ← one .txt per image: `class cx cy w h`, normalized
│                                (an empty .txt is a background image: class "Empty")
└── additional_info/           ← extra files, published as they are
    ├── lists/annotations.csv       one row per box (class, box, split, relative image path)
    └── statistics/statistics.csv   boxes and images per category and split
```

## Things it shows

- **Several boxes in one image**, and **images without any** (`Empty`): their label file
  is empty, which YOLO reads as a background image.
- **Authors with several affiliations**, joined with `; `.
- **`funding`**: free Markdown appended to the README's *Funding* section.
- **`additional_info/`**: everything extra in a dataset's root is published under this
  folder (so it can never collide with the generated `README.md`, `LICENSE` or
  `CITATION.cff`). Because this dataset already has an `additional_info/` folder *and*
  a loose file in its root (this `README.md`), the folder's contents end up in
  `additional_info/additional_info/` and this file in `additional_info/README.md`.

## Try it

```bash
wildintel-publisher product generate-metadata \
  --input-dir examples/yolo-dataset-extras --product-type yolo

wildintel-publisher hfh prepare \
  --input-dir examples/yolo-dataset-extras --output-dir /tmp/yolo-extras-out
```

Or pick `examples/yolo-dataset-extras` as a local directory in the web wizard's *AI
Dataset* flow.
