import cv2
import numpy as np
from PIL import Image


# ============================================================
# AYARLAR
# ============================================================

# Karşılaştırmayı daha düşük çözünürlükte yapıyoruz.
# Böylece birkaç piksellik/raster kayması daha az önemli hale geliyor.
COMPARE_SCALE = 0.35

# Küçük konum farklılıklarına tolerans.
#
# Bu değer karşılaştırma çözünürlüğündeki pixel değeridir.
# Örneğin 5-7 civarı küçük çizgi kaymalarını tolere eder.
TOLERANCE_PX = 6

# Fark maskesinde bundan küçük alanlar tamamen yok sayılır.
MIN_COMPONENT_AREA = 20

# Gerçek fark bölgelerini birbirine yaklaştırıp
# tek bir değişiklik bölgesi haline getirmek için kullanılır.
MERGE_KERNEL_SIZE = 9

# Görüntü karşılaştırmadan önce uygulanan blur.
BLUR_SIZE = 5

# Pixel farkı için eşik.
DIFF_THRESHOLD = 25


# ============================================================
# YARDIMCI FONKSİYONLAR
# ============================================================

def _to_gray(image):
    """
    OpenCV görüntüsünü grayscale yapar.
    """
    if len(image.shape) == 3:
        return cv2.cvtColor(
            image,
            cv2.COLOR_BGR2GRAY
        )

    return image


def _resize_for_compare(gray):
    """
    Karşılaştırma için görüntüyü küçültür.

    Orijinal PDF yüksek DPI ile render edilmiş olsa bile
    karşılaştırmayı daha düşük çözünürlükte yapıyoruz.
    """

    return cv2.resize(
        gray,
        None,
        fx=COMPARE_SCALE,
        fy=COMPARE_SCALE,
        interpolation=cv2.INTER_AREA
    )


def _prepare_image(gray):
    """
    Karşılaştırmadan önce görüntüyü hazırlar.
    """

    small = _resize_for_compare(gray)

    # Hafif blur:
    # PDF rasterizasyonundaki küçük çizgi kalınlığı
    # farklılıklarını azaltır.
    small = cv2.GaussianBlur(
        small,
        (BLUR_SIZE, BLUR_SIZE),
        0
    )

    return small


# ============================================================
# TOLERANSLI FARK HESAPLAMA
# ============================================================

def _create_difference_mask(
    old_gray,
    new_gray
):
    """
    İki grayscale görüntü arasında toleranslı fark maskesi oluşturur.

    Buradaki amaç:

        eski çizgi
        ------------
             ↓ birkaç pixel kaymış
        yeni çizgi
          ------------

    gibi durumları gerçek değişiklik kabul etmemektir.
    """

    # --------------------------------------------------------
    # Görüntüleri küçült
    # --------------------------------------------------------

    old_small = _prepare_image(
        old_gray
    )

    new_small = _prepare_image(
        new_gray
    )

    # --------------------------------------------------------
    # Boyut güvenliği
    # --------------------------------------------------------

    if old_small.shape != new_small.shape:

        new_small = cv2.resize(
            new_small,
            (
                old_small.shape[1],
                old_small.shape[0]
            ),
            interpolation=cv2.INTER_AREA
        )

    # --------------------------------------------------------
    # Normal pixel difference
    # --------------------------------------------------------

    diff = cv2.absdiff(
        old_small,
        new_small
    )

    # --------------------------------------------------------
    # Threshold
    # --------------------------------------------------------

    _, raw_diff = cv2.threshold(
        diff,
        DIFF_THRESHOLD,
        255,
        cv2.THRESH_BINARY
    )

    # --------------------------------------------------------
    # Biraz temizleme
    # --------------------------------------------------------

    small_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (3, 3)
    )

    raw_diff = cv2.morphologyEx(
        raw_diff,
        cv2.MORPH_OPEN,
        small_kernel,
        iterations=1
    )

    # ========================================================
    # MESAFE TABANLI TOLERANS
    # ========================================================

    # Eski ve yeni görüntülerde koyu çizgileri bul.
    #
    # Teknik çizimler genellikle beyaz arka plan + siyah çizgi
    # şeklinde olduğu için threshold kullanıyoruz.

    _, old_binary = cv2.threshold(
        old_small,
        220,
        255,
        cv2.THRESH_BINARY_INV
    )

    _, new_binary = cv2.threshold(
        new_small,
        220,
        255,
        cv2.THRESH_BINARY_INV
    )

    # --------------------------------------------------------
    # Küçük gürültüleri temizle
    # --------------------------------------------------------

    binary_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (3, 3)
    )

    old_binary = cv2.morphologyEx(
        old_binary,
        cv2.MORPH_OPEN,
        binary_kernel
    )

    new_binary = cv2.morphologyEx(
        new_binary,
        cv2.MORPH_OPEN,
        binary_kernel
    )

    # --------------------------------------------------------
    # Distance Transform
    # --------------------------------------------------------

    # old_binary'de çizgi olmayan alanların,
    # en yakın eski çizgiye uzaklığını hesaplıyoruz.

    old_inverse = cv2.bitwise_not(
        old_binary
    )

    new_inverse = cv2.bitwise_not(
        new_binary
    )

    old_distance = cv2.distanceTransform(
        old_inverse,
        cv2.DIST_L2,
        3
    )

    new_distance = cv2.distanceTransform(
        new_inverse,
        cv2.DIST_L2,
        3
    )

    # --------------------------------------------------------
    # Tolerans maskeleri
    # --------------------------------------------------------

    old_near = (
        old_distance <= TOLERANCE_PX
    ).astype(np.uint8) * 255

    new_near = (
        new_distance <= TOLERANCE_PX
    ).astype(np.uint8) * 255

    # --------------------------------------------------------
    # Eski / yeni çizgi bölgeleri
    # --------------------------------------------------------

    old_near = cv2.bitwise_and(
        old_near,
        old_binary
    )

    new_near = cv2.bitwise_and(
        new_near,
        new_binary
    )

    # --------------------------------------------------------
    # Gerçek değişiklik adayları
    # --------------------------------------------------------

    # Yeni görüntüde olup eski görüntüde karşılığı
    # olmayan alanlar.
    new_difference = cv2.bitwise_and(
        new_binary,
        cv2.bitwise_not(old_near)
    )

    # Eski görüntüde olup yeni görüntüde karşılığı
    # olmayan alanlar.
    old_difference = cv2.bitwise_and(
        old_binary,
        cv2.bitwise_not(new_near)
    )

    # --------------------------------------------------------
    # İki tarafı birleştir
    # --------------------------------------------------------

    geometric_diff = cv2.bitwise_or(
        new_difference,
        old_difference
    )

    # ========================================================
    # NORMAL PIXEL DIFF + GEOMETRIC DIFF
    # ========================================================

    # Raw pixel farkını çok baskın hale getirmiyoruz.
    #
    # Geometrik fark bizim ana sinyalimiz.
    #
    # Raw diff'i sadece destek olarak kullanıyoruz.

    geometric_diff = cv2.bitwise_or(
        geometric_diff,
        raw_diff
    )

    # --------------------------------------------------------
    # Küçük farkları temizle
    # --------------------------------------------------------

    clean_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (3, 3)
    )

    geometric_diff = cv2.morphologyEx(
        geometric_diff,
        cv2.MORPH_OPEN,
        clean_kernel,
        iterations=1
    )

    # --------------------------------------------------------
    # Yakın farkları birleştir
    # --------------------------------------------------------

    merge_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (
            MERGE_KERNEL_SIZE,
            MERGE_KERNEL_SIZE
        )
    )

    geometric_diff = cv2.dilate(
        geometric_diff,
        merge_kernel,
        iterations=1
    )

    geometric_diff = cv2.morphologyEx(
        geometric_diff,
        cv2.MORPH_CLOSE,
        merge_kernel,
        iterations=1
    )

    return geometric_diff


# ============================================================
# COMPONENT FİLTRELEME
# ============================================================

def _find_difference_boxes(
    mask,
    original_width,
    original_height
):
    """
    Fark maskesindeki componentleri bulur ve
    orijinal PDF koordinatlarına geri çevirir.
    """

    contours, _ = cv2.findContours(
        mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    boxes = []

    # Küçültülmüş görüntüden orijinale dönüş.
    scale_back = 1.0 / COMPARE_SCALE

    for contour in contours:

        area = cv2.contourArea(
            contour
        )

        if area < MIN_COMPONENT_AREA:
            continue

        x, y, w, h = cv2.boundingRect(
            contour
        )

        # Orijinal koordinatlara dön.
        x1 = int(
            x * scale_back
        )

        y1 = int(
            y * scale_back
        )

        x2 = int(
            (x + w) * scale_back
        )

        y2 = int(
            (y + h) * scale_back
        )

        # Sayfa sınırları
        x1 = max(
            0,
            min(
                x1,
                original_width - 1
            )
        )

        y1 = max(
            0,
            min(
                y1,
                original_height - 1
            )
        )

        x2 = max(
            0,
            min(
                x2,
                original_width
            )
        )

        y2 = max(
            0,
            min(
                y2,
                original_height
            )
        )

        if x2 <= x1 or y2 <= y1:
            continue

        boxes.append(
            (
                x1,
                y1,
                x2,
                y2
            )
        )

    # --------------------------------------------------------
    # Yukarıdan aşağıya ve soldan sağa sırala
    # --------------------------------------------------------

    boxes.sort(
        key=lambda box: (
            box[1],
            box[0]
        )
    )

    return boxes


# ============================================================
# TEK SAYFA KARŞILAŞTIRMA
# ============================================================

def compare_single_page(
    old_page: Image.Image,
    new_page: Image.Image,
    min_area: int = None
):
    """
    Sadece iki sayfayı karşılaştırır.

    Örneğin:

        Eski PDF -> 3. sayfa
        Yeni PDF -> 5. sayfa

    sadece bu iki sayfa karşılaştırılır.

    Returns:
        [
            (x1, y1, x2, y2),
            ...
        ]
    """

    # --------------------------------------------------------
    # PIL -> NumPy
    # --------------------------------------------------------

    old_np = np.array(
        old_page
    )

    new_np = np.array(
        new_page
    )

    # --------------------------------------------------------
    # RGB -> BGR
    # --------------------------------------------------------

    if len(old_np.shape) == 3:

        old_img = cv2.cvtColor(
            old_np,
            cv2.COLOR_RGB2BGR
        )

    else:

        old_img = old_np

    if len(new_np.shape) == 3:

        new_img = cv2.cvtColor(
            new_np,
            cv2.COLOR_RGB2BGR
        )

    else:

        new_img = new_np

    # --------------------------------------------------------
    # Boyut kontrolü
    # --------------------------------------------------------

    old_h, old_w = old_img.shape[:2]

    new_h, new_w = new_img.shape[:2]

    if (
        old_w != new_w
        or old_h != new_h
    ):

        print(
            "[COMPARE] "
            f"Boyut farklı: "
            f"Eski={old_w}x{old_h}, "
            f"Yeni={new_w}x{new_h}"
        )

        new_img = cv2.resize(
            new_img,
            (
                old_w,
                old_h
            ),
            interpolation=cv2.INTER_AREA
        )

    # --------------------------------------------------------
    # Grayscale
    # --------------------------------------------------------

    old_gray = _to_gray(
        old_img
    )

    new_gray = _to_gray(
        new_img
    )

    # --------------------------------------------------------
    # DIFFERENCE
    # --------------------------------------------------------

    mask = _create_difference_mask(
        old_gray,
        new_gray
    )

    # --------------------------------------------------------
    # Component alan filtresi
    # --------------------------------------------------------

    if min_area is not None:

        # Kullanıcı dışarıdan farklı bir alan
        # vermişse küçültülmüş görüntü için
        # yaklaşık karşılığını kullan.
        effective_area = max(
            1,
            int(
                min_area *
                COMPARE_SCALE *
                COMPARE_SCALE
            )
        )

        global MIN_COMPONENT_AREA

        old_min_area = MIN_COMPONENT_AREA

        MIN_COMPONENT_AREA = effective_area

        try:

            boxes = _find_difference_boxes(
                mask,
                old_w,
                old_h
            )

        finally:

            MIN_COMPONENT_AREA = old_min_area

    else:

        boxes = _find_difference_boxes(
            mask,
            old_w,
            old_h
        )

    # --------------------------------------------------------
    # Log
    # --------------------------------------------------------

    print(
        "[COMPARE] "
        f"{len(boxes)} fark bölgesi bulundu."
    )

    return boxes


# ============================================================
# ESKİ API
# ============================================================

def compare_pdf_pages(
    old_pages: list,
    new_pages: list,
    min_area: int = 150
):
    """
    Eski API.

    Eski ve yeni PDF'deki aynı indexli sayfaları karşılaştırır.

    Örneğin:

        old[0] <-> new[0]
        old[1] <-> new[1]
        old[2] <-> new[2]

    Yeni GUI'de tek sayfa karşılaştırması için
    compare_single_page() kullanılması önerilir.
    """

    detections = {}

    total_pages = min(
        len(old_pages),
        len(new_pages)
    )

    for idx in range(
        total_pages
    ):

        print(
            f"[COMPARE] "
            f"Sayfa {idx + 1}/{total_pages}"
        )

        boxes = compare_single_page(
            old_pages[idx],
            new_pages[idx],
            min_area=min_area
        )

        detections[
            (idx, idx)
        ] = boxes

    return detections