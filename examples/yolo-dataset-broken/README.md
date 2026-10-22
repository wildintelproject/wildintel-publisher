# YOLO dataset example that fails to be read

A tiny, deliberately broken YOLO dataset: pick it in the AI Dataset flow's **Select the folder**
step to see the structure checks fail. Everything else is fine, so each problem shows up on its
own:

| Check | What is wrong here | What the wizard says |
|---|---|---|
| `data.yaml` found and readable | — | passes |
| Splits and class names in data.yaml | — | passes |
| **nc matches the declared classes** | `nc: 5`, but `names` lists 3 classes | `nc is 5 but names lists 3 classes.` |
| **Images in the splits** | `images/val/` holds only a `notes.txt`, no image | `No images in images/val …` |
| **Label files well formed** | `labels/train/img_deer_001.txt` has a width of `1.7` (it must be between 0 and 1) and a line with 3 values instead of 4 | the file and line of each problem |

Since the structure has problems, the wizard shows them and does not let you go on to choose the
deeper checks.

```bash
wildintel-publisher product generate-metadata --input-dir examples/yolo-dataset-broken --product-type yolo
```
