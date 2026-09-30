"""
PDF Yükleme Modülü
~~~~~~~~~~~~~~~~~
PDF belgelerini yüksek çözünürlükte (DPI) rasterize ederek 
görüntü işleme ve karşılaştırma algoritmaları için PIL.Image formatında sunar.
"""

import os
from typing import List
try:
    import pymupdf
except ImportError:
    try:
        import fitz as pymupdf
    except ImportError:
        raise ImportError("PyMuPDF kütüphanesi bulunamadı. Lütfen aktif Python ortamınızda 'pip install pymupdf' komutunu çalıştırın.")

from PIL import Image


DEFAULT_DPI = 300


def load_pdf_pages(pdf_path: str, dpi: int = DEFAULT_DPI) -> List[Image.Image]:
    """
    Belirtilen PDF dosyasının tüm sayfalarını yüksek kalitede (varsayılan 300 DPI)
    render eder ve PIL Image listesi olarak döndürür.

    Args:
        pdf_path: PDF dosyasının tam dosya yolu.
        dpi: Render çözünürlüğü (görüntü işleme için 300 DPI önerilir).

    Returns:
        List[Image.Image]: Her bir sayfanın yüksek çözünürlüklü PIL Image nesnesi.
    """
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"PDF dosyası bulunamadı: {pdf_path}")

    pages: List[Image.Image] = []
    
    # PDF belgesini aç
    doc = pymupdf.open(pdf_path)
    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            # 300 DPI ile en yüksek detayda rasterize et
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            # Pixmap'i doğrudan RGB PIL Image'a dönüştür (RAM üzerinden, kayıpsız ve hızlı)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            pages.append(img)
    finally:
        doc.close()

    return pages


def load_single_page(pdf_path: str, page_number: int, dpi: int = DEFAULT_DPI) -> Image.Image:
    """
    PDF dosyasından yalnızca belirli bir sayfayı yüksek kalitede render eder.
    (0-tabanlı sayfa indeksi).
    """
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"PDF dosyası bulunamadı: {pdf_path}")

    doc = pymupdf.open(pdf_path)
    try:
        if page_number < 0 or page_number >= len(doc):
            raise IndexError(f"Geçersiz sayfa numarası: {page_number}. Toplam sayfa: {len(doc)}")
        
        page = doc[page_number]
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        return img
    finally:
        doc.close()


def get_pdf_page_count(pdf_path: str) -> int:
    """PDF dosyasındaki toplam sayfa sayısını döndürür."""
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"PDF dosyası bulunamadı: {pdf_path}")
    
    doc = pymupdf.open(pdf_path)
    try:
        return len(doc)
    finally:
        doc.close()
