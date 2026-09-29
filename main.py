"""
RevisionDetect - PDF Revizyon Karşılaştırma Aracı
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
İki PDF dosyasını karşılaştırarak değişen bölgeleri tespit eder
ve kutu içerisinde işaretler.

Kullanım:
    python main.py
"""

import customtkinter as ctk
from gui import RevisionDetectGUI


def main():
    root = ctk.CTk()
    app = RevisionDetectGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
