"""Remember an API key with Windows DPAPI; other systems keep it in memory only."""

import ctypes
import os
from ctypes import wintypes


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def crypt(value, decrypt=False):
    if os.name != "nt":
        raise OSError("Salvataggio protetto disponibile solo su Windows")
    buffer = ctypes.create_string_buffer(value)
    source = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    function = (
        ctypes.windll.crypt32.CryptUnprotectData
        if decrypt
        else ctypes.windll.crypt32.CryptProtectData
    )
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise OSError("Impossibile accedere alla chiave protetta di Windows")
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(result.data, ctypes.c_void_p))


def remember_key(path, key):
    encrypted = crypt(key.encode())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encrypted)


def restore_key(path):
    if not os.environ.get("OPENAI_API_KEY") and path.exists():
        try:
            os.environ["OPENAI_API_KEY"] = crypt(path.read_bytes(), decrypt=True).decode()
        except (OSError, UnicodeError):
            return False
    return bool(os.environ.get("OPENAI_API_KEY"))
