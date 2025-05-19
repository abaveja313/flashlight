import base64
from pathlib import Path


def image_to_data_uri(path: Path) -> str:
    # Read the raw bytes
    img_bytes = path.read_bytes()
    # Infer extension & MIME type
    ext = path.suffix.lower().lstrip('.')
    mime = f"image/{'jpeg' if ext in ('jpg', 'jpeg') else ext}"
    # Base64-encode and build the data URI
    b64 = base64.b64encode(img_bytes).decode('utf-8')
    return f"data:{mime};base64,{b64}"
