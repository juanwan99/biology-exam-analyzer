# -*- coding: utf-8 -*-
"""报告 URL 签名（HMAC-SHA256 + 过期戳）

防止学生答题质量报告被匿名遍历/枚举（PII 泄露）。报告 URL 由服务端
签发，download_report 校验签名 + 有效期。签名子密钥从 INTERNAL_API_SECRET
域分隔派生，与内部 API 密钥隔离——泄露其一不危及另一。
"""
import hashlib
import hmac
import os
import time
from typing import Optional

# 域分隔派生：报告签名子密钥 != 内部 API 密钥（HKDF 简化版）
_ROOT_SECRET = os.environ.get("INTERNAL_API_SECRET", "")
_REPORT_KEY = hashlib.sha256(
    b"biology-report-url-v1:" + _ROOT_SECRET.encode("utf-8")
).digest()

DEFAULT_TTL_SECONDS = 24 * 3600  # 报告链接有效期 24 小时


def _compute_sig(filename: str, exp: int) -> str:
    """HMAC-SHA256(filename:exp)，截断 128 bit（32 hex），足够防伪造且 URL 更短。"""
    msg = f"{filename}:{exp}".encode("utf-8")
    return hmac.new(_REPORT_KEY, msg, hashlib.sha256).hexdigest()[:32]


def sign_report_path(filename: str, ttl: int = DEFAULT_TTL_SECONDS) -> str:
    """给报告文件名签发查询串 'sig=..&exp=..'。filename 不含路径前缀。"""
    exp = int(time.time()) + ttl
    return f"sig={_compute_sig(filename, exp)}&exp={exp}"


def verify_report_sig(filename: str, sig: Optional[str], exp: Optional[str]) -> bool:
    """校验签名 + 有效期。任一缺失/过期/不符/secret 未注入 → False（fail-closed）。"""
    if not _ROOT_SECRET or not sig or not exp:
        return False
    try:
        exp_int = int(exp)
    except (ValueError, TypeError):
        return False
    if exp_int < int(time.time()):
        return False
    return hmac.compare_digest(_compute_sig(filename, exp_int), sig)
