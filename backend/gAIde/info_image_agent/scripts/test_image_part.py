from __future__ import annotations

import sys
import mimetypes

from google.genai import types as T


def main(path: str) -> None:
    with open(path, "rb") as f:
        data = f.read()
    mime, _ = mimetypes.guess_type(path)
    if mime is None:
        mime = "image/jpeg"
    print("mime:", mime)
    print("Trying Image.from_bytes...")
    try:
        img = T.Image.from_bytes(mime_type=mime, data=data)
        print("image part created via Image:", img)
        return
    except Exception as e:
        print("Image.from_bytes failed:", repr(e))
    print("Trying Part.from_bytes...")
    try:
        part = T.Part.from_bytes(data, mime_type=mime)
        print("image part created via Part.from_bytes:", part)
        return
    except Exception as e:
        print("Part.from_bytes failed:", repr(e))
    print("Trying Blob -> Part.from_blob...")
    try:
        blob = T.Blob(mime_type=mime, data=data)
        part = T.Part.from_blob(blob)
        print("image part created via Blob->Part:", part)
        return
    except Exception as e:
        print("Blob->Part failed:", repr(e))
        raise SystemExit(2)


if __name__ == "__main__":
    main(sys.argv[1])
