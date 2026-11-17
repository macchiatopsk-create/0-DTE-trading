# -*- coding: utf-8 -*-
"""앱(웹) 푸시 보내기 — RFC 8291(aes128gcm 암호화) + RFC 8292(VAPID). 외부 서비스·앱 설치 없음.

설정값(저장소 시크릿 PUSH_CONFIG)은 폰의 앱 화면 '🔔 알림 켜기'가 만들어 준다:
  base64(JSON {"s": PushSubscription.toJSON(), "k": VAPID 개인키 d(base64url)})
여러 기기는 공백으로 이어 붙인다. 개인키는 폰에서 만들어지고 시크릿에만 들어간다 (레포·채팅에 안 남음).
"""
import base64, json, os, struct, time, urllib.request, urllib.error
from urllib.parse import urlparse

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def unb64u(s):
    s = s.strip()
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _pub_raw(key):
    return key.public_key().public_bytes(serialization.Encoding.X962,
                                         serialization.PublicFormat.UncompressedPoint)


def _hkdf(salt, info, length, ikm):
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def encrypt(payload, p256dh, auth, salt=None, as_key=None):
    """RFC 8291 aes128gcm 본문 (헤더 + 암호문 한 레코드)."""
    ua_pub = unb64u(p256dh)
    auth = unb64u(auth)
    as_key = as_key or ec.generate_private_key(ec.SECP256R1())
    as_pub = _pub_raw(as_key)
    shared = as_key.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub))
    ikm = _hkdf(auth, b"WebPush: info\x00" + ua_pub + as_pub, 32, shared)
    salt = salt or os.urandom(16)
    cek = _hkdf(salt, b"Content-Encoding: aes128gcm\x00", 16, ikm)
    nonce = _hkdf(salt, b"Content-Encoding: nonce\x00", 12, ikm)
    ct = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)      # 마지막 레코드 구분자 0x02, 패딩 없음
    return salt + struct.pack(">I", 4096) + bytes([len(as_pub)]) + as_pub + ct


def vapid_header(endpoint, d_b64u, sub):
    """Authorization: vapid t=<JWT ES256>, k=<공개키>"""
    key = ec.derive_private_key(int.from_bytes(unb64u(d_b64u), "big"), ec.SECP256R1())
    u = urlparse(endpoint)
    head = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    body = b64u(json.dumps({"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + 12 * 3600,
                            "sub": sub}, separators=(",", ":")).encode())
    r, s = decode_dss_signature(key.sign(f"{head}.{body}".encode(), ec.ECDSA(hashes.SHA256())))
    sig = b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return f"vapid t={head}.{body}.{sig}, k={b64u(_pub_raw(key))}"


def parse_config(raw):
    """시크릿 값 → [(subscription, vapid_d), ...]"""
    out = []
    for tok in (raw or "").split():
        try:
            j = json.loads(tok) if tok.lstrip().startswith("{") else json.loads(base64.b64decode(tok + "=" * (-len(tok) % 4)))
            out.append((j["s"], j["k"]))
        except Exception as e:
            print(f"  앱 푸시 설정값 읽기 실패: {type(e).__name__}")
    return out


def send(raw_config, title, body, url, tag=None, sub_claim=None, ttl=900):
    """설정된 모든 기기로 보낸다. 성공한 기기 수를 돌려준다."""
    n = 0
    payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag or title[:40]},
                         ensure_ascii=False).encode("utf-8")
    for sub, d in parse_config(raw_config):
        try:
            data = encrypt(payload, sub["keys"]["p256dh"], sub["keys"]["auth"])
            req = urllib.request.Request(sub["endpoint"], data=data, method="POST", headers={
                "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream",
                "TTL": str(ttl), "Urgency": "high",
                "Authorization": vapid_header(sub["endpoint"], d, sub_claim or url)})
            urllib.request.urlopen(req, timeout=10).read()
            n += 1
        except urllib.error.HTTPError as e:
            why = "구독 만료 — 앱에서 🔔 다시 설정" if e.code in (404, 410) else e.read()[:120]
            print(f"  앱 푸시 실패 {e.code}: {why}")
        except Exception as e:
            print(f"  앱 푸시 실패: {type(e).__name__}: {e}")
    return n
