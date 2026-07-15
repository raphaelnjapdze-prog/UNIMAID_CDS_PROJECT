# scripts/

Standalone developer utilities — run by hand from the repo root, not imported by the
app and not collected by `pytest` (they live outside `tests/`). Each script puts the
repo root on `sys.path` so `utils.*` imports resolve when run directly.

## `test_image_qc.py`

Runs the image quality-control check — the same `utils.image_quality_control.assess_image_quality()`
the Diagnostics page runs before AI screening — against a specimen photo, so you can
see why a given image is (or isn't) flagged.

```bash
python scripts/test_image_qc.py path/to/specimen.jpg
python scripts/test_image_qc.py path/to/specimen.jpg --save enhanced.jpg
```

Prints `Passed`, the reason, and the blur/exposure scores when the report carries them.
`--save` writes the enhanced/processed image for inspection. Exit codes: `0` pass,
`1` fail, `2` usage/IO error (e.g. the image can't be opened) — usable in a pipeline.
