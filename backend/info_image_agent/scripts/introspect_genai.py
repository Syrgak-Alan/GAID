from __future__ import annotations

import inspect

try:
    from google import genai
    from google.genai import types as T
except Exception as e:
    print("Import error:", e)
    raise

print("genai.Client:", genai.Client)
names = [
    "Image",
    "Part",
    "InputImage",
    "Blob",
    "Content",
    "TextPart",
    "BlobPart",
]
for n in names:
    print(n, getattr(T, n, None))

members = [n for n, _ in inspect.getmembers(T) if not n.startswith("_")]
print("\nType members (first 120):")
print(members[:120])

