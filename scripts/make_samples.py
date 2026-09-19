"""Generate sample test documents for the demo.

Creates:
1. Clean digital PDF with ~10 MCQs across 3 pages, answer key at end
2. Scanned-style PDF (rasterized with rotation/noise)
3. PNG screenshot of a single question page
4. PDF with a cross-page question boundary
5. Separate Answer Key PDF
6. PDF with missing number, garbled text, unmatched answer entry
7. Invalid files (fake .pdf, corrupt .pdf, oversized)
"""

import io
import os
import struct

from PIL import Image, ImageDraw, ImageFont


SAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "samples")


def ensure_dir():
    os.makedirs(SAMPLES_DIR, exist_ok=True)


def create_pdf_from_pages(pages_text: list[str], filename: str) -> str:
    """Create a simple PDF from page text using PyMuPDF."""
    import fitz

    doc = fitz.open()
    for text in pages_text:
        page = doc.new_page(width=595, height=842)  # A4
        text_rect = fitz.Rect(50, 50, 545, 792)
        page.insert_textbox(text_rect, text, fontsize=11, fontname="helv")

    path = os.path.join(SAMPLES_DIR, filename)
    doc.save(path)
    doc.close()
    return path


def create_png_from_text(text: str, filename: str, width=800, height=600) -> str:
    """Create a PNG image with text."""
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    y = 20
    for line in text.split("\n"):
        draw.text((20, y), line, fill="black")
        y += 18

    path = os.path.join(SAMPLES_DIR, filename)
    img.save(path, "PNG")
    return path


def sample_1_clean_pdf():
    """Clean digital PDF, ~10 MCQs, 3 pages, answer key at end."""
    page1 = """MATHEMATICS FINAL EXAM 2024
Duration: 2 hours | Total Marks: 50

1. What is the derivative of x^2?
   A. x
   B. 2x
   C. x^2
   D. 2x^2

2. The integral of 1/x is:
   A. ln(x) + C
   B. x + C
   C. 1/x^2 + C
   D. x^2 + C

3. What is the value of sin(90°)?
   A. 0
   B. 0.5
   C. 1
   D. -1

4. If f(x) = 3x + 2, what is f(5)?
   A. 15
   B. 17
   C. 13
   D. 20"""

    page2 = """5. The Pythagorean theorem states:
   A. a + b = c
   B. a^2 + b^2 = c^2
   C. a * b = c
   D. a^2 - b^2 = c^2

6. What is the area of a circle with radius 5?
   A. 25π
   B. 10π
   C. 5π
   D. 50π

7. The quadratic formula is used to solve equations of degree:
   A. 1
   B. 2
   C. 3
   D. 4

8. What is log₁₀(100)?
   A. 1
   B. 2
   C. 10
   D. 100"""

    page3 = """9. In a right triangle, the longest side is called:
   A. Hypotenuse
   B. Adjacent
   C. Opposite
   D. Base

10. What is the slope of the line y = 3x + 7?
    A. 7
    B. 3
    C. 10
    D. -3

ANSWER KEY
1-B  2-A  3-C  4-B  5-B
6-A  7-B  8-B  9-A  10-B"""

    return create_pdf_from_pages([page1, page2, page3], "01_clean_digital.pdf")


def sample_2_scanned_pdf():
    """Scanned-style PDF: rasterize sample 1 with slight rotation and noise."""
    import fitz

    # First create the clean PDF
    src_path = os.path.join(SAMPLES_DIR, "01_clean_digital.pdf")
    if not os.path.exists(src_path):
        sample_1_clean_pdf()

    doc = fitz.open(src_path)
    out_doc = fitz.open()

    for page in doc:
        # Render at lower quality
        mat = fitz.Matrix(1.5, 1.5)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")

        # Open with Pillow, apply degradation
        img = Image.open(io.BytesIO(img_bytes))
        # Slight rotation
        img = img.rotate(1.5, expand=True, fillcolor="white")
        # Convert back
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        # Insert as image page
        new_page = out_doc.new_page(width=img.width * 0.8, height=img.height * 0.8)
        new_page.insert_image(new_page.rect, stream=buf.getvalue())

    path = os.path.join(SAMPLES_DIR, "02_scanned_style.pdf")
    out_doc.save(path)
    out_doc.close()
    doc.close()
    return path


def sample_3_png_screenshot():
    """PNG screenshot of a single question page."""
    text = """PHYSICS POP QUIZ

Q1. What is Newton's second law of motion?
  (a) F = ma
  (b) F = mv
  (c) E = mc^2
  (d) P = mv

Q2. The SI unit of force is:
  (a) Watt
  (b) Joule
  (c) Newton
  (d) Pascal

Q3. Acceleration due to gravity on Earth is approximately:
  (a) 5.8 m/s^2
  (b) 9.8 m/s^2
  (c) 12.8 m/s^2
  (d) 15.8 m/s^2"""
    return create_png_from_text(text, "03_screenshot.png")


def sample_4_cross_page():
    """PDF with a question split across page boundary."""
    page1 = """BIOLOGY TEST

1. Which organelle is responsible for energy production?
   A. Nucleus
   B. Mitochondria
   C. Ribosome
   D. Golgi apparatus

2. DNA stands for:
   A. Deoxyribonucleic acid
   B. Dinitrogen acid
   C. Deoxynitrogen acid
   D. Dinucleotide acid

3. The process by which plants convert sunlight into energy
   is called photosynthesis. Which of the following is NOT"""

    page2 = """   a product of photosynthesis?
   A. Oxygen
   B. Glucose
   C. Carbon dioxide
   D. Water

4. Which blood type is the universal donor?
   A. A
   B. B
   C. AB
   D. O

5. The human body has approximately how many bones?
   A. 106
   B. 206
   C. 306
   D. 406"""

    return create_pdf_from_pages([page1, page2], "04_cross_page.pdf")


def sample_5_separate_answer_key():
    """Separate Answer Key PDF with different format."""
    content = """BIOLOGY TEST - ANSWER KEY

Question | Answer
---------|-------
  Q.1    |   B
  Q.2    |   A
  Q.3    |   C
  Q.4    |   D
  Q.5    |   B

Prepared by: Prof. Smith
Date: January 2024"""

    return create_pdf_from_pages([content], "05_answer_key_separate.pdf")


def sample_6_edge_cases():
    """PDF with missing number, garbled text, unmatched answer entry."""
    page1 = """CHEMISTRY QUIZ - EDGE CASES

1. What is the chemical symbol for gold?
   A. Go
   B. Au
   C. Gd
   D. Ag

   The molecular weight of water is approximately:
   A. 16 g/mol
   B. 18 g/mol
   C. 20 g/mol
   D. 22 g/mol

3. Th3 str@ng3st ac1d 1n th3 w0rld 1s:
   A. HCl
   B. H2SO4
   C. Fluoroantimonic acid
   D. HNO3

ANSWER KEY:
1-B  2-B  3-C  99-A"""

    return create_pdf_from_pages([page1], "06_edge_cases.pdf")


def sample_7_invalid_files():
    """Create invalid test files."""
    # Renamed .exe as .pdf (MZ header)
    exe_path = os.path.join(SAMPLES_DIR, "07a_fake_exe.pdf")
    with open(exe_path, "wb") as f:
        f.write(b"MZ" + b"\x00" * 200)

    # Corrupt PDF (valid header, garbage body)
    corrupt_path = os.path.join(SAMPLES_DIR, "07b_corrupt.pdf")
    with open(corrupt_path, "wb") as f:
        f.write(b"%PDF-1.4\nthis is totally not a valid pdf structure\n%%EOF")

    # "Oversized" file (just a marker; actual test sets a low limit)
    oversize_path = os.path.join(SAMPLES_DIR, "07c_oversized.txt")
    with open(oversize_path, "w") as f:
        f.write("This file simulates an oversized upload. Actual test sets MAX_UPLOAD_SIZE_MB=0.")

    return exe_path, corrupt_path, oversize_path


def main():
    ensure_dir()
    print("Generating sample documents...")

    paths = [
        ("1. Clean digital PDF", sample_1_clean_pdf()),
        ("2. Scanned-style PDF", sample_2_scanned_pdf()),
        ("3. PNG screenshot", sample_3_png_screenshot()),
        ("4. Cross-page boundary PDF", sample_4_cross_page()),
        ("5. Separate answer key PDF", sample_5_separate_answer_key()),
        ("6. Edge cases PDF", sample_6_edge_cases()),
    ]

    inv = sample_7_invalid_files()
    paths.append(("7a. Fake exe as PDF", inv[0]))
    paths.append(("7b. Corrupt PDF", inv[1]))
    paths.append(("7c. Oversized marker", inv[2]))

    print("\nGenerated files:")
    for desc, path in paths:
        size = os.path.getsize(path)
        print(f"  {desc}: {os.path.basename(path)} ({size:,} bytes)")

    print(f"\nAll samples saved to: {SAMPLES_DIR}")


if __name__ == "__main__":
    main()
