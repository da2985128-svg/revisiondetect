# gui.py - Performans ve Tema Düzeltmeli Versiyon
import customtkinter as ctk
from tkinter import filedialog, messagebox, Canvas
from PIL import Image, ImageTk, ImageDraw
import os
import threading
import queue
from pdf_loader import load_pdf_pages
from diff_engine import compare_pdf_pages


ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

THEMES = {
    "light": {
        "bg":          "#f5f7fa",
        "card":        "#ffffff",
        "primary":     "#3b82f6",
        "primary_hov": "#2563eb",
        "danger":      "#ef4444",
        "success":     "#22c55e",
        "text":        "#1e293b",
        "text_sec":    "#64748b",
        "border":      "#e2e8f0",
        "canvas_bg":   "#e8ecf1",
        "placeholder": "#94a3b8",
        "nav_btn":     "#e2e8f0",
        "nav_btn_hov": "#cbd5e1",
        "status_bg":   "#e2e8f0",
        "entry_bg":    "#f8fafc",
        "box_old":     "#ef4444",
        "box_new":     "#22c55e",
    },
    "dark": {
        "bg":          "#0f172a",
        "card":        "#1e293b",
        "primary":     "#3b82f6",
        "primary_hov": "#2563eb",
        "danger":      "#f87171",
        "success":     "#4ade80",
        "text":        "#f1f5f9",
        "text_sec":    "#94a3b8",
        "border":      "#334155",
        "canvas_bg":   "#1e293b",
        "placeholder": "#475569",
        "nav_btn":     "#334155",
        "nav_btn_hov": "#475569",
        "status_bg":   "#1e293b",
        "entry_bg":    "#0f172a",
        "box_old":     "#f87171",
        "box_new":     "#4ade80",
    },
}


def _colors() -> dict:
    mode = ctk.get_appearance_mode()
    return THEMES["dark"] if mode == "Dark" else THEMES["light"]


class RevisionDetectGUI:
    CANVAS_W = 460
    CANVAS_H = 540

    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title("RevisionDetect - PDF Revizyon Karşılaştırma")
        self.root.geometry("1020x820")
        self.root.minsize(920, 720)

        C = _colors()
        self.root.configure(fg_color=C["bg"])

        self.old_pdf_path = ctk.StringVar(value="")
        self.new_pdf_path = ctk.StringVar(value="")

        self.old_pages: list[Image.Image] = []
        self.new_pages: list[Image.Image] = []
        self.old_page_idx = 0
        self.new_page_idx = 0

        self.detections: dict = {}

        self._old_photo = None
        self._new_photo = None

        # Zoom & Pan Durum Değişkenleri
        self.zoom_scale = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._drag_start_x = 0
        self._drag_start_y = 0

        # Performans için önbellek
        self._cached_render = {}

        self._queue: queue.Queue = queue.Queue()

        self._build_ui()
        self._process_queue()

    def _build_ui(self):
        C = _colors()

        # Header
        header = ctk.CTkFrame(self.root, fg_color=C["primary"], corner_radius=0, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text="📄  RevisionDetect",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color="white",
        ).pack(side="left", padx=20)

        self.theme_btn = ctk.CTkButton(
            header, text="🌙", width=36, height=36,
            fg_color="transparent", hover_color=C["primary_hov"],
            font=ctk.CTkFont(size=16), command=self._toggle_theme,
        )
        self.theme_btn.pack(side="right", padx=16)

        # Body
        self.body = ctk.CTkFrame(self.root, fg_color=C["bg"], corner_radius=0)
        self.body.pack(fill="both", expand=True, padx=16, pady=(12, 8))

        # Dosya Kartı
        self.file_card = self._card(self.body)
        self.file_card.pack(fill="x", pady=(0, 10))

        self._file_row(self.file_card, "Eski PDF  (Orijinal)", self.old_pdf_path, self._browse_old)
        self._file_row(self.file_card, "Yeni PDF  (Güncel)",   self.new_pdf_path, self._browse_new)

        # Aksiyon ve Zoom Butonları
        action_row = ctk.CTkFrame(self.body, fg_color="transparent")
        action_row.pack(fill="x", pady=(0, 10))

        self.compare_btn = ctk.CTkButton(
            action_row, text="🔍  Karşılaştır", width=140, height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=C["primary"], hover_color=C["primary_hov"],
            corner_radius=10, command=self._on_compare,
        )
        self.compare_btn.pack(side="left")

        self.export_btn = ctk.CTkButton(
            action_row, text="💾  Farkları Kaydet", width=150, height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=C["success"], hover_color="#16a34a", text_color="white",
            corner_radius=10, command=self._on_export_pdf,
        )
        self.export_btn.pack(side="left", padx=(8, 0))

        self.clear_btn = ctk.CTkButton(
            action_row, text="🗑  Temizle", width=100, height=38,
            font=ctk.CTkFont(size=13),
            fg_color=C["nav_btn"], hover_color=C["nav_btn_hov"], text_color=C["text"],
            corner_radius=10, command=self._on_clear,
        )
        self.clear_btn.pack(side="left", padx=(8, 0))

        # ZOOM KONTROLLERİ
        zoom_frame = ctk.CTkFrame(action_row, fg_color="transparent")
        zoom_frame.pack(side="right")

        ctk.CTkButton(
            zoom_frame, text="➕", width=34, height=34, corner_radius=8,
            fg_color=C["nav_btn"], hover_color=C["nav_btn_hov"], text_color=C["text"],
            command=lambda: self._apply_zoom(1.25),
        ).pack(side="left", padx=2)

        # Dinamik Renkli Yüzde Etiketi (Tema Değişiminde Otomatik Uyum Sağlar)
        self.lbl_zoom = ctk.CTkLabel(
            zoom_frame, text="100%", width=46,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#1e293b", "#f1f5f9")
        )
        self.lbl_zoom.pack(side="left", padx=2)

        ctk.CTkButton(
            zoom_frame, text="➖", width=34, height=34, corner_radius=8,
            fg_color=C["nav_btn"], hover_color=C["nav_btn_hov"], text_color=C["text"],
            command=lambda: self._apply_zoom(0.8),
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            zoom_frame, text="🔍 Sığdır", width=65, height=34, corner_radius=8,
            fg_color=C["nav_btn"], hover_color=C["nav_btn_hov"], text_color=C["text"],
            command=self._reset_zoom,
        ).pack(side="left", padx=(4, 8))

        self.diff_badge = ctk.CTkLabel(
            zoom_frame, text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=C["danger"],
        )
        self.diff_badge.pack(side="left", padx=6)

        # Görsel Alanı
        self.viewer_card = self._card(self.body)
        self.viewer_card.pack(fill="both", expand=True)

        self.viewer_card.columnconfigure(0, weight=1)
        self.viewer_card.columnconfigure(1, weight=1)
        self.viewer_card.rowconfigure(0, weight=1)

        # Sol Canvas (Eski PDF)
        left = ctk.CTkFrame(self.viewer_card, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=6)
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        self.lbl_title_old = ctk.CTkLabel(left, text="Eski (Orijinal)", font=ctk.CTkFont(size=13, weight="bold"), text_color=("#1e293b", "#f1f5f9"))
        self.lbl_title_old.grid(row=0, column=0, sticky="w", padx=4)

        self.canvas_old = Canvas(left, width=self.CANVAS_W, height=self.CANVAS_H, bg=C["canvas_bg"], highlightthickness=0, bd=0)
        self.canvas_old.grid(row=1, column=0, sticky="nsew", pady=(4, 6))

        nav_old = ctk.CTkFrame(left, fg_color="transparent")
        nav_old.grid(row=2, column=0)
        self.btn_prev_old = ctk.CTkButton(nav_old, text="◀", width=36, height=30, corner_radius=8, fg_color=C["nav_btn"], hover_color=C["nav_btn_hov"], text_color=C["text"], command=lambda: self._change_page("old", -1))
        self.btn_prev_old.pack(side="left", padx=2)
        self.lbl_page_old = ctk.CTkLabel(nav_old, text="— / —", font=ctk.CTkFont(size=12), text_color=C["text_sec"])
        self.lbl_page_old.pack(side="left", padx=10)
        self.btn_next_old = ctk.CTkButton(nav_old, text="▶", width=36, height=30, corner_radius=8, fg_color=C["nav_btn"], hover_color=C["nav_btn_hov"], text_color=C["text"], command=lambda: self._change_page("old", 1))
        self.btn_next_old.pack(side="left", padx=2)

        # Sağ Canvas (Yeni PDF)
        right = ctk.CTkFrame(self.viewer_card, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=6)
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        self.lbl_title_new = ctk.CTkLabel(right, text="Yeni (Güncel)", font=ctk.CTkFont(size=13, weight="bold"), text_color=("#1e293b", "#f1f5f9"))
        self.lbl_title_new.grid(row=0, column=0, sticky="w", padx=4)

        self.canvas_new = Canvas(right, width=self.CANVAS_W, height=self.CANVAS_H, bg=C["canvas_bg"], highlightthickness=0, bd=0)
        self.canvas_new.grid(row=1, column=0, sticky="nsew", pady=(4, 6))

        nav_new = ctk.CTkFrame(right, fg_color="transparent")
        nav_new.grid(row=2, column=0)
        self.btn_prev_new = ctk.CTkButton(nav_new, text="◀", width=36, height=30, corner_radius=8, fg_color=C["nav_btn"], hover_color=C["nav_btn_hov"], text_color=C["text"], command=lambda: self._change_page("new", -1))
        self.btn_prev_new.pack(side="left", padx=2)
        self.lbl_page_new = ctk.CTkLabel(nav_new, text="— / —", font=ctk.CTkFont(size=12), text_color=C["text_sec"])
        self.lbl_page_new.pack(side="left", padx=10)
        self.btn_next_new = ctk.CTkButton(nav_new, text="▶", width=36, height=30, corner_radius=8, fg_color=C["nav_btn"], hover_color=C["nav_btn_hov"], text_color=C["text"], command=lambda: self._change_page("new", 1))
        self.btn_next_new.pack(side="left", padx=2)

        # Canvas Etkileşimleri (Pan ve Ctrl + MouseWheel Zoom)
        for canvas in (self.canvas_old, self.canvas_new):
            canvas.bind("<ButtonPress-1>", self._on_pan_start)
            canvas.bind("<B1-Motion>", self._on_pan_drag)
            canvas.bind("<Control-MouseWheel>", self._on_ctrl_mouse_wheel)
            canvas.bind("<Control-Button-4>", lambda e: self._apply_zoom(1.15))
            canvas.bind("<Control-Button-5>", lambda e: self._apply_zoom(0.85))

        # Status Bar
        self.status_bar = ctk.CTkFrame(self.root, fg_color=C["status_bg"], corner_radius=0, height=30)
        self.status_bar.pack(fill="x", side="bottom")
        self.status_bar.pack_propagate(False)

        self.status_label = ctk.CTkLabel(self.status_bar, text="Hazır — Lütfen iki PDF dosyası seçin.", font=ctk.CTkFont(size=11), text_color=C["text_sec"])
        self.status_label.pack(side="left", padx=14, pady=3)

        self._draw_placeholder(self.canvas_old, "Eski PDF sayfası\nburada görünecek")
        self._draw_placeholder(self.canvas_new, "Yeni PDF sayfası\nburada görünecek")
        self._update_nav_state("old")
        self._update_nav_state("new")

    # ================================================================== #
    #  ZOOM & PAN İŞLEMLERİ (ULTRA HIZLI VE AKICI)
    # ================================================================== #
    def _apply_zoom(self, factor: float):
        new_scale = self.zoom_scale * factor
        if 0.4 <= new_scale <= 6.0:
            self.zoom_scale = new_scale
            self.lbl_zoom.configure(text=f"{int(self.zoom_scale * 100)}%")
            self.show_page("old")
            self.show_page("new")

    def _reset_zoom(self):
        self.zoom_scale = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.lbl_zoom.configure(text="100%")
        self.show_page("old")
        self.show_page("new")

    def _on_ctrl_mouse_wheel(self, event):
        """Yalnızca Ctrl tuşuna basılıyken tekerlek ile hızlı zoom yapar."""
        if event.delta > 0:
            self._apply_zoom(1.15)
        else:
            self._apply_zoom(0.85)

    def _on_pan_start(self, event):
        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def _on_pan_drag(self, event):
        dx = event.x - self._drag_start_x
        dy = event.y - self._drag_start_y
        self.pan_x += dx
        self.pan_y += dy
        self._drag_start_x = event.x
        self._drag_start_y = event.y
        self.show_page("old", redraw_img=False)
        self.show_page("new", redraw_img=False)

    # ================================================================== #
    #  SAYFA GÖRÜNTÜLEME VE OPTİMİZE DÖNÜŞTÜRME
    # ================================================================== #
    def show_page(self, side: str, redraw_img: bool = True):
        C = _colors()
        if side == "old":
            pages, idx, canvas = self.old_pages, self.old_page_idx, self.canvas_old
            box_color = C["box_old"]
        else:
            pages, idx, canvas = self.new_pages, self.new_page_idx, self.canvas_new
            box_color = C["box_new"]

        canvas.delete("all")

        if not pages:
            placeholder = "Eski PDF sayfası\nburada görünecek" if side == "old" else "Yeni PDF sayfası\nburada görünecek"
            self._draw_placeholder(canvas, placeholder)
            self._update_nav_state(side)
            return

        cw = canvas.winfo_width() or self.CANVAS_W
        ch = canvas.winfo_height() or self.CANVAS_H

        orig = pages[idx]
        cache_key = (side, idx, round(self.zoom_scale, 2), cw, ch)

        if redraw_img or cache_key not in self._cached_render:
            fit_scale = min(cw / orig.width, ch / orig.height)
            final_scale = fit_scale * self.zoom_scale
            target_w = max(1, int(orig.width * final_scale))
            target_h = max(1, int(orig.height * final_scale))

            # Hızlı Resampling Algorithm (BILINEAR) - Anında Zoom Sağlar
            img = orig.copy().resize((target_w, target_h), Image.BILINEAR)
            photo = ImageTk.PhotoImage(img)
            self._cached_render[cache_key] = (photo, target_w, target_h)
        else:
            photo, target_w, target_h = self._cached_render[cache_key]

        if side == "old":
            self._old_photo = photo
        else:
            self._new_photo = photo

        cx = (cw // 2) + int(self.pan_x)
        cy = (ch // 2) + int(self.pan_y)

        canvas.create_image(cx, cy, image=photo, anchor="center")

        # Bounding Box çizimleri
        key = (self.old_page_idx, self.new_page_idx)
        if key in self.detections:
            ox = cx - target_w // 2
            oy = cy - target_h // 2
            sx = target_w / orig.width
            sy = target_h / orig.height

            for box in self.detections[key]:
                x1, y1, x2, y2 = box
                canvas.create_rectangle(
                    ox + x1 * sx, oy + y1 * sy,
                    ox + x2 * sx, oy + y2 * sy,
                    outline=box_color, width=2, dash=(6, 3),
                )

        self._update_nav_state(side)

    # ================================================================== #
    #  PDF DIŞA AKTARMA (FARKLARI KAYDET)
    # ================================================================== #
    def _on_export_pdf(self):
        if not self.detections:
            messagebox.showwarning("Uyarı", "Henüz karşılaştırma yapılmadı veya hiç fark bulunamadı.")
            return

        save_path = filedialog.asksaveasfilename(
            title="İşaretlenmiş PDF'i Kaydet",
            defaultextension=".pdf",
            filetypes=[("PDF Dosyası", "*.pdf")],
        )
        if not save_path:
            return

        self.status_label.configure(text="⏳ İşaretlenmiş PDF oluşturuluyor, lütfen bekleyin...")

        def _worker():
            try:
                annotated_pages = []
                for idx, orig_img in enumerate(self.new_pages):
                    img_copy = orig_img.copy().convert("RGB")
                    draw = ImageDraw.Draw(img_copy)

                    for (old_p, new_p), boxes in self.detections.items():
                        if new_p == idx:
                            for (x1, y1, x2, y2) in boxes:
                                draw.rectangle([x1, y1, x2, y2], outline="#22c55e", width=6)

                    annotated_pages.append(img_copy)

                if annotated_pages:
                    annotated_pages[0].save(
                        save_path,
                        save_all=True,
                        append_images=annotated_pages[1:],
                        resolution=300.0,
                    )
                    self._queue.put((messagebox.showinfo, ("Başarılı", f"İşaretlenmiş PDF başarıyla kaydedildi:\n{save_path}")))
                    self._queue.put((self.status_label.configure, ({"text": "Hazır — PDF başarıyla kaydedildi."},)))
            except Exception as e:
                self._queue.put((messagebox.showerror, ("Hata", f"PDF kaydedilirken bir hata oluştu:\n{e}")))

        threading.Thread(target=_worker, daemon=True).start()

    # ================================================================== #
    #  YARDIMCI METOTLAR
    # ================================================================== #
    def _card(self, parent) -> ctk.CTkFrame:
        C = _colors()
        return ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=14, border_width=1, border_color=C["border"])

    def _file_row(self, parent, label, var, command):
        C = _colors()
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(8, 4))

        ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=12), text_color=C["text_sec"]).pack(anchor="w")

        inner = ctk.CTkFrame(row, fg_color="transparent")
        inner.pack(fill="x", pady=(2, 0))

        entry = ctk.CTkEntry(
            inner, textvariable=var, height=36, corner_radius=10,
            font=ctk.CTkFont(size=12), border_color=C["border"],
            fg_color=C["entry_bg"], text_color=C["text"],
        )
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            inner, text="Gözat…", width=80, height=36,
            font=ctk.CTkFont(size=12), corner_radius=10,
            fg_color=C["nav_btn"], hover_color=C["nav_btn_hov"], text_color=C["text"],
            command=command,
        ).pack(side="right")

    def _draw_placeholder(self, canvas: Canvas, text: str):
        C = _colors()
        canvas.delete("all")
        cx = canvas.winfo_width() // 2 or self.CANVAS_W // 2
        cy = canvas.winfo_height() // 2 or self.CANVAS_H // 2
        canvas.create_text(cx, cy, text=text, fill=C["placeholder"], font=("Segoe UI", 13), justify="center")

    def _update_nav_state(self, side: str):
        if side == "old":
            pages, idx = self.old_pages, self.old_page_idx
            btn_prev, btn_next, lbl = self.btn_prev_old, self.btn_next_old, self.lbl_page_old
        else:
            pages, idx = self.new_pages, self.new_page_idx
            btn_prev, btn_next, lbl = self.btn_prev_new, self.btn_next_new, self.lbl_page_new

        if not pages:
            lbl.configure(text="— / —")
            btn_prev.configure(state="disabled")
            btn_next.configure(state="disabled")
            return

        lbl.configure(text=f"{idx + 1} / {len(pages)}")
        btn_prev.configure(state="normal" if idx > 0 else "disabled")
        btn_next.configure(state="normal" if idx < len(pages) - 1 else "disabled")

    def _change_page(self, side: str, delta: int):
        if side == "old" and self.old_pages:
            new_idx = self.old_page_idx + delta
            if 0 <= new_idx < len(self.old_pages):
                self.old_page_idx = new_idx
                self.show_page("old")
        elif side == "new" and self.new_pages:
            new_idx = self.new_page_idx + delta
            if 0 <= new_idx < len(self.new_pages):
                self.new_page_idx = new_idx
                self.show_page("new")

    def _browse_old(self):
        path = filedialog.askopenfilename(title="Eski PDF Dosyasını Seçin", filetypes=[("PDF", "*.pdf"), ("Tümü", "*.*")])
        if path:
            self.old_pdf_path.set(path)
            self._load_pdf("old", path)

    def _browse_new(self):
        path = filedialog.askopenfilename(title="Yeni PDF Dosyasını Seçin", filetypes=[("PDF", "*.pdf"), ("Tümü", "*.*")])
        if path:
            self.new_pdf_path.set(path)
            self._load_pdf("new", path)

    def _process_queue(self):
        try:
            while True:
                fn, args = self._queue.get_nowait()
                fn(*args)
        except queue.Empty:
            pass
        self.root.after(50, self._process_queue)

    def _load_pdf(self, side: str, path: str):
        if not path or not os.path.isfile(path):
            return

        label_name = "Eski PDF" if side == "old" else "Yeni PDF"
        self.status_label.configure(text=f"⏳ {label_name} taranıyor (300 DPI)...")

        def _worker():
            try:
                pages = load_pdf_pages(path, dpi=300)
                self._queue.put((self._on_pdf_loaded, (side, pages)))
            except Exception as e:
                self._queue.put((self._on_pdf_load_error, (side, str(e))))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_pdf_loaded(self, side: str, pages: list[Image.Image]):
        self._cached_render.clear()
        if side == "old":
            self.old_pages = pages
            self.old_page_idx = 0
            self.show_page("old")
        else:
            self.new_pages = pages
            self.new_page_idx = 0
            self.show_page("new")
        self._update_status()

    def _on_pdf_load_error(self, side: str, error_msg: str):
        messagebox.showerror("Hata", f"PDF yükleme hatası:\n{error_msg}")

    def _on_compare(self):
        old = self.old_pdf_path.get().strip()
        new = self.new_pdf_path.get().strip()

        if not old or not new or not self.old_pages or not self.new_pages:
            messagebox.showwarning("Uyarı", "Lütfen her iki PDF dosyasının da yüklendiğinden emin olun.")
            return

        self.status_label.configure(text="⏳ Karşılaştırma yapılıyor, lütfen bekleyin...")
        self.diff_badge.configure(text="")

        def _worker():
            try:
                detections = compare_pdf_pages(self.old_pages, self.new_pages)
                self._queue.put((self.set_detections, (detections,)))
            except Exception as e:
                self._queue.put((messagebox.showerror, ("Hata", f"Karşılaştırma hatası:\n{e}")))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_clear(self):
        self.old_pdf_path.set("")
        self.new_pdf_path.set("")
        self.old_pages.clear()
        self.new_pages.clear()
        self.old_page_idx = 0
        self.new_page_idx = 0
        self.detections.clear()
        self._cached_render.clear()
        self._reset_zoom()
        self.diff_badge.configure(text="")
        self._draw_placeholder(self.canvas_old, "Eski PDF sayfası\nburada görünecek")
        self._draw_placeholder(self.canvas_new, "Yeni PDF sayfası\nburada görünecek")
        self._update_nav_state("old")
        self._update_nav_state("new")
        self.status_label.configure(text="Hazır — Lütfen iki PDF dosyası seçin.")

    def _toggle_theme(self):
        mode = ctk.get_appearance_mode()
        ctk.set_appearance_mode("dark" if mode == "Light" else "light")
        self.root.after(50, self._apply_theme_colors)

    def _apply_theme_colors(self):
        C = _colors()
        mode = ctk.get_appearance_mode()
        self.theme_btn.configure(text="☀️" if mode == "Dark" else "🌙")
        self.root.configure(fg_color=C["bg"])
        self.body.configure(fg_color=C["bg"])
        self.canvas_old.configure(bg=C["canvas_bg"])
        self.canvas_new.configure(bg=C["canvas_bg"])
        self.file_card.configure(fg_color=C["card"], border_color=C["border"])
        self.viewer_card.configure(fg_color=C["card"], border_color=C["border"])
        self.lbl_zoom.configure(text_color=C["text"])
        self.lbl_title_old.configure(text_color=C["text"])
        self.lbl_title_new.configure(text_color=C["text"])
        self.show_page("old")
        self.show_page("new")

    def _update_status(self):
        old_cnt, new_cnt = len(self.old_pages), len(self.new_pages)
        if old_cnt > 0 and new_cnt > 0:
            self.status_label.configure(text=f"Hazır — Eski PDF ({old_cnt} sayfa) ve Yeni PDF ({new_cnt} sayfa) yüklendi.")
        else:
            self.status_label.configure(text="Lütfen iki PDF dosyasını da yükleyin.")

    def set_detections(self, detections: dict):
        self.detections = detections
        total = sum(len(v) for v in detections.values())
        self.diff_badge.configure(text=f"🔴 {total} fark bulundu" if total else "✅ Fark bulunamadı")
        self.show_page("old")
        self.show_page("new")
        self.status_label.configure(text=f"Karşılaştırma tamamlandı — Toplam {total} fark tespit edildi.")