# diff_engine.py
import cv2
import numpy as np
from PIL import Image

def compare_images(
    img1_pil: Image.Image, 
    img2_pil: Image.Image, 
    min_area: int = 150, 
    threshold_val: int = 30
) -> list[tuple[int, int, int, int]]:
    """
    İki PIL görseli arasındaki farkları tespit eder ve sınırlayıcı kutuları döndürür.
    
    Returns:
        List[Tuple[int, int, int, int]]: [(x1, y1, x2, y2), ...] formatında kutu koordinatları.
    """
    # PIL Image -> NumPy / OpenCV Gri Tonlama
    img1 = cv2.cvtColor(np.array(img1_pil), cv2.COLOR_RGB2GRAY)
    img2 = cv2.cvtColor(np.array(img2_pil), cv2.COLOR_RGB2GRAY)

    # Görsel boyutları farklıysa 2. görseli 1.ye göre yeniden boyutlandır
    if img1.shape != img2.shape:
        img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))

    # 1. Mutlak Fark (Absolute Difference)
    diff = cv2.absdiff(img1, img2)

    # 2. Eşikleme (Thresholding) - Küçük piksel değişimlerini süzme
    _, thresh = cv2.threshold(diff, threshold_val, 255, cv2.THRESH_BINARY)

    # 3. Morfolojik Genişletme (Dilation) - Birbirine yakın noktaları tek kutuda birleştirme
    kernel = np.ones((5, 5), np.uint8)
    thresh = cv2.dilate(thresh, kernel, iterations=2)

    # 4. Kontur Tespiti
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    for cnt in contours:
        # Belirlenen alandan (min_area) küçük gürültüleri göz ardı et
        if cv2.contourArea(cnt) >= min_area:
            x, y, w, h = cv2.boundingRect(cnt)
            boxes.append((x, y, x + w, y + h))  # (x1, y1, x2, y2)

    return boxes


def compare_pdf_pages(
    old_pages: list[Image.Image], 
    new_pages: list[Image.Image]
) -> dict:
    """
    Tüm sayfaları sırayla karşılaştırıp gui.py'nin beklediği 'detections' sözlüğünü üretir.
    """
    detections = {}
    max_pages = max(len(old_pages), len(new_pages))

    for i in range(max_pages):
        if i < len(old_pages) and i < len(new_pages):
            boxes = compare_images(old_pages[i], new_pages[i])
            if boxes:
                detections[(i, i)] = boxes

    return detections