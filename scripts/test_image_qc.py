"""Run the image quality-control check on a specimen photo and print the report.

    python scripts/test_image_qc.py path/to/specimen.jpg
    python scripts/test_image_qc.py path/to/specimen.jpg --save enhanced.jpg

Exits 0 if the image passes QC, 1 if it fails, 2 on a usage/IO error. This is the
same assess_image_quality() the Diagnostics page runs before screening; use it to
eyeball why a given photo is (or isn't) flagged.
"""

import argparse
import sys
from pathlib import Path

# The script lives in scripts/, so the repo root isn't on sys.path when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, UnidentifiedImageError  # noqa: E402

from utils.image_quality_control import assess_image_quality  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the image quality-control check on a specimen photo."
    )
    parser.add_argument("image", help="Path to the specimen photo (JPG/PNG).")
    parser.add_argument(
        "--save",
        metavar="PATH",
        help="Write the enhanced/processed image here for inspection.",
    )
    args = parser.parse_args()

    try:
        img = Image.open(args.image)
    except (FileNotFoundError, UnidentifiedImageError, OSError) as e:
        print(f"Could not open image {args.image!r}: {e}", file=sys.stderr)
        return 2

    report = assess_image_quality(img)

    print("Passed:", report["passed"])
    print("Reason:", report["reason"])
    # Scores are only reported on the pass path; print whichever the report carries.
    for key in ("blur_score", "exposure_score"):
        if key in report:
            print(f"{key}: {report[key]:.4f}")

    if args.save and report.get("processed_image") is not None:
        report["processed_image"].save(args.save)
        print(f"Processed image written to {args.save}")

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
