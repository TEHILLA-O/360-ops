"""Small text PDF writer for audit exports. No external PDF dependency."""

from __future__ import annotations


def render_pdf(lines: list[str]) -> bytes:
    pages: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        safe = "".join(ch if 32 <= ord(ch) < 127 else "?" for ch in line)[:110]
        current.append(safe)
        if len(current) == 46:
            pages.append(current)
            current = []
    if current or not pages:
        pages.append(current)
    contents = []
    for page in pages:
        commands = ["BT", "/F1 9 Tf", "48 780 Td", "12 TL"]
        for line in page:
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            commands.append(f"({escaped}) '")
        commands.append("ET")
        contents.append("\n".join(commands).encode("latin-1", errors="replace"))
    objects: list[bytes] = [b"", b"<< /Type /Catalog /Pages 2 0 R >>", b""]
    font_object = len(objects)
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")
    content_numbers = []
    for stream in contents:
        content_numbers.append(len(objects))
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream")
    page_numbers = []
    for index in range(len(pages)):
        page_numbers.append(len(objects))
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Contents {content_numbers[index]} 0 R "
                f"/Resources << /Font << /F1 {font_object} 0 R >> >> >>"
            ).encode("latin-1")
        )
    kids = " ".join(f"{number} 0 R" for number in page_numbers)
    objects[2] = f"<< /Type /Pages /Count {len(page_numbers)} /Kids [{kids}] >>".encode("latin-1")
    encoded = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects[1:], start=1):
        offsets.append(len(encoded))
        encoded.extend(f"{number} 0 obj\n".encode("latin-1"))
        encoded.extend(obj)
        encoded.extend(b"\nendobj\n")
    xref = len(encoded)
    encoded.extend(f"xref\n0 {len(objects)}\n".encode("latin-1"))
    encoded.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        encoded.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    encoded.extend(
        f"trailer << /Size {len(objects)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode("latin-1")
    )
    return bytes(encoded)
