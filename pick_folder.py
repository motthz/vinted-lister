import sys
import tkinter as tk
from tkinter import filedialog

sys.stdout.reconfigure(encoding="utf-8")
root = tk.Tk()
root.withdraw()
root.attributes("-topmost", True)
folder = filedialog.askdirectory(title="Scegli la cartella con i capi")
root.destroy()
print(folder)
