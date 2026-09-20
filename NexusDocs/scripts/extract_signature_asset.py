"""Extract a signature from the supplied scan without redrawing or resampling it."""

from pathlib import Path
import argparse

from PIL import Image, ImageOps
from pypdf import PdfReader


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--crop",
        type=int,
        nargs=4,
        metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"),
        help="Exact pixel bounds in the embedded 300 dpi scan.",
    )
    args = parser.parse_args()
    if args.source.suffix.casefold() == ".pdf":
        source = PdfReader(args.source).pages[0].images[0].image.convert("L")
    else:
        # Accept a native-resolution Poppler render for JBIG2-only PDF scans.
        source = Image.open(args.source).convert("L")
    width, height = source.size

    if args.crop:
        left, top, right, bottom = args.crop
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise ValueError(
                f"Область {tuple(args.crop)} выходит за границы скана "
                f"{width} x {height}."
            )
        crop = source.crop((left, top, right, bottom))
        trim_to_ink = False
    else:
        # Backwards-compatible default for the retained Tsomartov scan: the
        # lower of its two signatures, followed by a tight content crop.
        crop = source.crop(
            (
                int(width * .29),
                int(height * .445),
                int(width * .56),
                int(height * .601),
            )
        )
        trim_to_ink = True

    ink = ImageOps.invert(crop)
    content_mask = ink.point(lambda value: 255 if value > 100 else 0)
    bbox = content_mask.getbbox()
    if bbox is None:
        raise ValueError("В выбранной области скана не найдена подпись.")
    if trim_to_ink:
        crop = crop.crop(bbox)

    alpha = ImageOps.invert(crop).point(
        lambda value: 0 if value < 35 else min(255, int((value - 35) * 255 / 220))
    )
    result = Image.new("RGBA", crop.size, (0, 0, 0, 255))
    result.putalpha(alpha)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.save(args.output, dpi=(300, 300))
    print(
        f"Extracted signature from {width} x {height} scan: "
        f"{result.width} x {result.height}"
    )


if __name__ == "__main__":
    main()
