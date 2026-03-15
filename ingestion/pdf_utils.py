"""
PDF Utilities — Text extraction and image conversion
"""

from pathlib import Path
from typing import Optional

import pdfplumber
from loguru import logger


def extract_text_from_pdf(file_path: str) -> list[str]:
    """
    Extract text from each page of a PDF using pdfplumber.
    Returns a list of strings, one per page.
    """
    texts = []
    try:
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                texts.append(text)
                logger.debug(f"Page {i + 1}: extracted {len(text)} characters")
    except Exception as e:
        logger.error(f"Failed to extract text from {file_path}: {e}")
        raise

    return texts


def extract_page_count(file_path: str) -> int:
    """Get the number of pages in a PDF."""
    try:
        with pdfplumber.open(file_path) as pdf:
            return len(pdf.pages)
    except Exception as e:
        logger.error(f"Failed to get page count for {file_path}: {e}")
        raise


def extract_tables_from_pdf(file_path: str) -> list[list[list[str]]]:
    """
    Extract tables from each page of a PDF.
    Returns a list of tables per page. Each table is a list of rows.
    """
    all_tables = []
    try:
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages):
                tables = page.extract_tables() or []
                all_tables.extend(tables)
                logger.debug(f"Page {i + 1}: found {len(tables)} tables")
    except Exception as e:
        logger.error(f"Failed to extract tables from {file_path}: {e}")
        raise

    return all_tables


def pdf_to_images(file_path: str, dpi: int = 200) -> list[str]:
    """
    Convert PDF pages to images using pdf2image.
    Returns list of image file paths saved to a temp directory.
    Requires poppler to be installed for pdf2image.
    """
    try:
        from pdf2image import convert_from_path

        output_dir = Path(file_path).parent / "page_images"
        output_dir.mkdir(parents=True, exist_ok=True)

        images = convert_from_path(file_path, dpi=dpi)
        image_paths = []

        for i, img in enumerate(images):
            img_path = output_dir / f"page_{i + 1}.png"
            img.save(str(img_path), "PNG")
            image_paths.append(str(img_path))
            logger.debug(f"Saved page {i + 1} image: {img_path}")

        return image_paths

    except ImportError:
        logger.warning("pdf2image not available — poppler may not be installed. Skipping image conversion.")
        return []
    except Exception as e:
        logger.error(f"Failed to convert PDF to images: {e}")
        return []


def extract_text_with_positions(file_path: str) -> list[dict]:
    """
    Extract text with bounding box positions for each word.
    Useful for spatial analysis and field location.
    """
    results = []
    try:
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages):
                words = page.extract_words() or []
                for word in words:
                    results.append({
                        "page": i + 1,
                        "text": word.get("text", ""),
                        "x0": word.get("x0", 0),
                        "y0": word.get("top", 0),
                        "x1": word.get("x1", 0),
                        "y1": word.get("bottom", 0),
                    })
    except Exception as e:
        logger.error(f"Failed to extract text positions from {file_path}: {e}")
        raise

    return results
