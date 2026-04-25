import base64

from Crypto.Cipher import AES, DES
from Crypto.Util.Padding import pad, unpad


LOCAL_DES_KEY = "u2oh6Vu^"
LOGIN_AES_KEY = "u2oh6Vu^HWe4_AES"


def encrypt_local_password(password: str) -> str:
    key = LOCAL_DES_KEY.encode("utf-8")
    cipher = DES.new(key, DES.MODE_CBC, iv=key)
    return cipher.encrypt(pad(password.encode("utf-8"), DES.block_size)).hex()


def decrypt_local_password(cipher_hex: str) -> str:
    try:
        encrypted = bytes.fromhex(cipher_hex)
    except ValueError:
        return cipher_hex
    key = LOCAL_DES_KEY.encode("utf-8")
    for cipher in (
        DES.new(key, DES.MODE_CBC, iv=key),
        DES.new(key, DES.MODE_ECB),
    ):
        try:
            plain = unpad(cipher.decrypt(encrypted), DES.block_size)
            return plain.decode("utf-8")
        except ValueError:
            continue
    return cipher_hex


def encrypt_login_value(value: str) -> str:
    key = LOGIN_AES_KEY.encode("utf-8")
    cipher = AES.new(key, AES.MODE_CBC, iv=key)
    encrypted = cipher.encrypt(pad(value.encode("utf-8"), AES.block_size))
    return base64.b64encode(encrypted).decode("utf-8")
