import base64
import re


def validate_output(output):
    name = output.get("name", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.(md|txt|csv|png|jpe?g)", name):
        raise ValueError("Invalid artifact filename")
    data = base64.b64decode(output.get("content_base64", ""), validate=True)
    if not data or len(data) > 1000000:
        raise ValueError("Artifact must be nonempty and at most 1 MB")
    if name.endswith(".png") and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Invalid PNG image")
    if name.endswith((".jpg", ".jpeg")) and not data.startswith(b"\xff\xd8\xff"):
        raise ValueError("Invalid JPEG image")
    if name.endswith((".md", ".txt", ".csv")):
        text = data.decode("utf-8")
        if "\x00" in text:
            raise ValueError("Artifact contains null bytes")
    return name, data
