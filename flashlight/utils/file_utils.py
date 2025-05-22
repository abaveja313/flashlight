import base64
from pathlib import Path


def image_to_data_uri(path: Path, delete: bool = False) -> str:
    """
    Converts an image file to a Base64-encoded data URI format. This function reads the image
    file from the specified path, infers its MIME type based on the file extension, encodes the
    image file into a Base64 string, and constructs the data URI. Optionally, the original file
    can be deleted after processing.

    Parameters:
        path (Path): The file path of the image to be converted.
        delete (bool): If set to True, deletes the original image file after conversion. Defaults
            to False.

    Returns:
        str: A Base64-encoded data URI representation of the image.
    """
    # Read the raw bytes
    img_bytes = path.read_bytes()
    # Infer extension & MIME type
    ext = path.suffix.lower().lstrip(".")
    mime = f"image/{'jpeg' if ext in ('jpg', 'jpeg') else ext}"
    # Base64-encode and build the data URI
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    return f"data:{mime};base64,{b64}"
