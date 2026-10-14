"""
Utility to generate sample PDF files for testing and faculty templates.
Generates:
1. sample_students.pdf: A valid text-based student register PDF.
2. sample_scanned.pdf: An image-only / textless PDF to test scanned document detection.
"""

from pathlib import Path
import pypdf
from pypdf.generic import DecodedStreamObject, NameObject, DictionaryObject


def create_sample_text_pdf(output_path: Path):
    """Create a text-based PDF containing structured student list."""
    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    lines = [
        "DEPARTMENT OF COMPUTER SCIENCE & ENGINEERING",
        "STUDENT ADMISSION AND ATTENDANCE REGISTER - 2026",
        "--------------------------------------------------------------------------------",
        "Roll No: 101 | Name: Rahul Sharma | Class: CSE | Section: A",
        "Roll No: 102 | Name: Priya Verma | Class: CSE | Section: A",
        "Roll No: 103 | Name: Aman Patel | Class: CSE | Section: A",
        "Roll No: 104 | Name: Sneha Kulkarni | Class: CSE | Section: A",
        "Roll No: 105 | Name: Vikram Singh | Class: CSE | Section: A",
        "Roll No: 106 | Name: Ananya Iyer | Class: CSE | Section: B",
        "Roll No: 107 | Name: Rohan Gupta | Class: CSE | Section: B",
        "Roll No: 108 | Name: Meera Nair | Class: CSE | Section: B",
        "Roll No: 109 | Name: Kavya Reddy | Class: ECE | Section: A",
        "Roll No: 110 | Name: Arjun Das | Class: ECE | Section: A",
        "--------------------------------------------------------------------------------",
        "Page 1 of 1"
    ]

    stream_content = ["BT", "/F1 11 Tf", "50 740 Td"]
    for i, line in enumerate(lines):
        # Escape parenthesis
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if i == 0:
            stream_content.append(f"({escaped}) Tj")
        else:
            stream_content.append(f"0 -20 Td ({escaped}) Tj")
    stream_content.append("ET")

    content_str = "\n".join(stream_content)
    content_stream = DecodedStreamObject()
    content_stream.set_data(content_str.encode("latin1"))

    font_dict = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica")
    })
    resources = DictionaryObject({
        NameObject("/Font"): DictionaryObject({
            NameObject("/F1"): font_dict
        })
    })

    page[NameObject("/Contents")] = content_stream
    page[NameObject("/Resources")] = resources

    with open(output_path, "wb") as f:
        writer.write(f)


def create_sample_scanned_pdf(output_path: Path):
    """Create a blank / textless PDF representing a scanned image."""
    writer = pypdf.PdfWriter()
    # Add a blank page with no text content stream
    writer.add_blank_page(width=612, height=792)
    with open(output_path, "wb") as f:
        writer.write(f)


if __name__ == "__main__":
    templates_dir = Path(__file__).resolve().parent
    create_sample_text_pdf(templates_dir / "sample_students.pdf")
    create_sample_scanned_pdf(templates_dir / "sample_scanned.pdf")
    print("Sample PDF templates successfully created.")
