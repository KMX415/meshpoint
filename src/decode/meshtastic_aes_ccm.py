"""Meshtastic firmware-compatible AES-CCM (hostapd aes-ccm.cpp port)."""

from __future__ import annotations

from Crypto.Cipher import AES  # nosec B413

AES_BLOCK_SIZE = 16
_CCM_L = 2


def _put_be16(buf: bytearray, offset: int, val: int) -> None:
    buf[offset] = (val >> 8) & 0xFF
    buf[offset + 1] = val & 0xFF


def _xor_block(dst: bytearray, src: bytes | bytearray) -> None:
    for i in range(AES_BLOCK_SIZE):
        dst[i] ^= src[i]


def _constant_time_compare(a: bytearray, b: bytearray, length: int) -> bool:
    if length == 0:
        return True
    diff = 0
    for i in range(length):
        diff |= a[i] ^ b[i]
    return diff == 0


class MeshtasticAesCcmEngine:
    """AES-CCM with fixed L=2, matching Meshtastic src/mesh/aes-ccm.cpp."""

    def __init__(self, key: bytes) -> None:
        if len(key) not in (16, 32):
            raise ValueError("AES key must be 16 or 32 bytes")
        self._cipher = AES.new(key, AES.MODE_ECB)

    def _encrypt_block(self, block: bytearray) -> bytearray:
        return bytearray(self._cipher.encrypt(bytes(block)))

    def encrypt(
        self,
        nonce: bytes,
        mac_len: int,
        plaintext: bytes,
        aad: bytes = b"",
    ) -> tuple[bytes, bytes]:
        """Return ciphertext and authentication tag."""
        if len(aad) > 30 or mac_len > AES_BLOCK_SIZE:
            raise ValueError("invalid CCM parameters")

        x = bytearray(AES_BLOCK_SIZE)
        a = bytearray(AES_BLOCK_SIZE)

        self._auth_start(mac_len, nonce, aad, len(plaintext), x)
        self._auth(plaintext, x)

        self._encr_start(nonce, a)
        crypt = bytearray(len(plaintext))
        self._encr(plaintext, crypt, a)

        auth = bytearray(mac_len)
        self._encr_auth(mac_len, x, a, auth)
        return bytes(crypt), bytes(auth)

    def decrypt(
        self,
        nonce: bytes,
        mac_len: int,
        ciphertext: bytes,
        auth: bytes,
        aad: bytes = b"",
    ) -> bytes | None:
        if len(aad) > 30 or mac_len > AES_BLOCK_SIZE:
            return None

        x = bytearray(AES_BLOCK_SIZE)
        a = bytearray(AES_BLOCK_SIZE)
        t = bytearray(AES_BLOCK_SIZE)

        self._encr_start(nonce, a)
        self._decr_auth(mac_len, a, auth, t)

        plain = bytearray(len(ciphertext))
        self._encr(ciphertext, plain, a)

        self._auth_start(mac_len, nonce, aad, len(ciphertext), x)
        self._auth(bytes(plain), x)

        if not _constant_time_compare(x, t, mac_len):
            return None
        return bytes(plain)

    def _auth_start(
        self,
        mac_len: int,
        nonce: bytes,
        aad: bytes,
        plain_len: int,
        x: bytearray,
    ) -> None:
        b = bytearray(AES_BLOCK_SIZE)
        b[0] = 0x40 if aad else 0
        b[0] |= (((mac_len - 2) // 2) << 3)
        b[0] |= (_CCM_L - 1)
        b[1 : 1 + (15 - _CCM_L)] = nonce[: 15 - _CCM_L]
        _put_be16(b, AES_BLOCK_SIZE - _CCM_L, plain_len)

        x[:] = self._encrypt_block(b)

        if not aad:
            return

        aad_buf = bytearray(2 * AES_BLOCK_SIZE)
        _put_be16(aad_buf, 0, len(aad))
        aad_buf[2 : 2 + len(aad)] = aad
        _xor_block(aad_buf, x)
        x[:] = self._encrypt_block(aad_buf)

        if len(aad) > AES_BLOCK_SIZE - 2:
            tail = bytearray(aad_buf[AES_BLOCK_SIZE : 2 * AES_BLOCK_SIZE])
            _xor_block(tail, x)
            x[:] = self._encrypt_block(tail)

    def _auth(self, data: bytes, x: bytearray) -> None:
        offset = 0
        while offset + AES_BLOCK_SIZE <= len(data):
            _xor_block(x, data[offset : offset + AES_BLOCK_SIZE])
            x[:] = self._encrypt_block(x)
            offset += AES_BLOCK_SIZE

        last = len(data) - offset
        if last:
            block = bytearray(AES_BLOCK_SIZE)
            block[:last] = data[offset : offset + last]
            _xor_block(x, block)
            x[:] = self._encrypt_block(x)

    def _encr_start(self, nonce: bytes, a: bytearray) -> None:
        a[0] = _CCM_L - 1
        a[1 : 1 + (15 - _CCM_L)] = nonce[: 15 - _CCM_L]

    def _encr(self, inp: bytes, out: bytearray, a: bytearray) -> None:
        offset = 0
        counter = 1
        while offset + AES_BLOCK_SIZE <= len(inp):
            _put_be16(a, AES_BLOCK_SIZE - 2, counter)
            keystream = self._encrypt_block(a)
            for i in range(AES_BLOCK_SIZE):
                out[offset + i] = keystream[i] ^ inp[offset + i]
            offset += AES_BLOCK_SIZE
            counter += 1

        last = len(inp) - offset
        if last:
            _put_be16(a, AES_BLOCK_SIZE - 2, counter)
            keystream = self._encrypt_block(a)
            for i in range(last):
                out[offset + i] = keystream[i] ^ inp[offset + i]

    def _encr_auth(self, mac_len: int, x: bytearray, a: bytearray, auth: bytearray) -> None:
        _put_be16(a, AES_BLOCK_SIZE - 2, 0)
        tmp = self._encrypt_block(a)
        for i in range(mac_len):
            auth[i] = x[i] ^ tmp[i]

    def _decr_auth(self, mac_len: int, a: bytearray, auth: bytes, t: bytearray) -> None:
        _put_be16(a, AES_BLOCK_SIZE - 2, 0)
        tmp = self._encrypt_block(a)
        for i in range(mac_len):
            t[i] = auth[i] ^ tmp[i]
