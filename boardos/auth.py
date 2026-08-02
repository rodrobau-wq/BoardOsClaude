"""Autenticação: hash de senha (pbkdf2) + tokens JWT (HS256).

- Senhas nunca em texto: pbkdf2_hmac(sha256) com salt por usuário.
- Token assina {sub, nome, tenant_id, papel, exp} com BOARDOS_SECRET.
  O servidor deriva o tenant do token — o cliente NUNCA escolhe o tenant.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt

SECRET = os.environ.get("BOARDOS_SECRET", "dev-inseguro-trocar-em-producao")
TOKEN_HORAS = 12
_ITER = 200_000


def hash_password(senha: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, _ITER)
    return "pbkdf2$%d$%s$%s" % (_ITER, base64.b64encode(salt).decode(),
                               base64.b64encode(dk).decode())


def verify_password(senha: str, stored: str) -> bool:
    try:
        _algo, iters, salt_b64, hash_b64 = stored.split("$")
        salt = base64.b64decode(salt_b64)
        dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, int(iters))
        return hmac.compare_digest(base64.b64encode(dk).decode(), hash_b64)
    except Exception:
        return False


def make_token(sub: str, nome: str, tenant_id: str, papel: str) -> str:
    payload = {
        "sub": sub, "nome": nome, "tenant_id": tenant_id, "papel": papel,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_HORAS),
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET, algorithms=["HS256"])
