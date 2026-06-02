"""积分服务 — 对接 momowan.xyz 主站积分系统（zhixue-server internal API）。"""
import os
import httpx
from logger import get_logger

logger = get_logger()

_ZHIXUE_API = "https://api.momowan.xyz/api/credits/internal"
_INTERNAL_SECRET = os.environ.get("INTERNAL_API_SECRET", "")

ANALYSIS_COST = 200  # 每份试卷消耗积分


def _headers():
    return {"X-Internal-Secret": _INTERNAL_SECRET, "Content-Type": "application/json"}


async def get_balance(user_id: int) -> int:
    """查询用户积分余额。"""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{_ZHIXUE_API}/balance",
            params={"userId": user_id},
            headers=_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(data.get("error", "余额查询失败"))
        return data["data"]["balance"]


async def consume(user_id: int, credits: int = ANALYSIS_COST, description: str = "智能审题分析") -> dict:
    """扣除积分。返回 {creditsUsed, balance}。余额不足时抛出 InsufficientCreditsError。"""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{_ZHIXUE_API}/paper-consume",
            headers=_headers(),
            json={
                "userId": user_id,
                "credits": credits,
                "stage": "bio_analysis",
                "description": description,
            },
        )
        data = resp.json()
        if resp.status_code == 402:
            raise InsufficientCreditsError(
                balance=data.get("data", {}).get("balance", 0),
                required=credits,
            )
        resp.raise_for_status()
        if not data.get("success"):
            raise RuntimeError(data.get("error", "扣费失败"))
        logger.info(f"[积分] 用户 {user_id} 扣费 {credits}，余额 {data['data']['balance']}")
        return data["data"]


async def verify_token(token: str) -> dict:
    """通过主站 /api/user/profile 验证 JWT token，返回 {id, email, nickname, ...}。"""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://api.momowan.xyz/api/user/profile",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 401:
            raise InvalidTokenError("登录已过期，请重新登录")
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise InvalidTokenError("认证失败")
        return data["data"]


class InsufficientCreditsError(Exception):
    def __init__(self, balance: int, required: int):
        self.balance = balance
        self.required = required
        super().__init__(f"积分不足：余额 {balance}，需要 {required}")


class InvalidTokenError(Exception):
    pass
