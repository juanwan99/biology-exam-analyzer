"""
用户认证和操作日志API
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import bcrypt
import secrets
import string

from database import get_db
from models import AdminUser, OperationLog
from logger import get_logger

logger = get_logger()

router = APIRouter(prefix="/api/auth", tags=["认证管理"])

# 简单的token存储（生产环境应使用Redis）
active_tokens: Dict[str, dict] = {}

# 登录限流：IP -> (失败次数, 首次失败时间)
_login_attempts: Dict[str, tuple] = {}
LOGIN_MAX_ATTEMPTS = 5      # 最多 5 次
LOGIN_WINDOW_SECONDS = 60   # 60 秒窗口
TOKEN_TTL_SECONDS = 86400    # token 有效期 24h


# ============ Pydantic Models ============

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    user: Optional[dict] = None
    message: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class UserCreate(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None
    role: str = "editor"


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[int] = None


class OperationLogQuery(BaseModel):
    page: int = 1
    page_size: int = 50
    username: Optional[str] = None
    operation: Optional[str] = None
    target_type: Optional[str] = None


# ============ 认证相关 ============

def generate_random_password(length=12):
    """生成随机密码"""
    chars = string.ascii_letters + string.digits + "!@#$%"
    return ''.join(secrets.choice(chars) for _ in range(length))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def hash_password(password: str) -> str:
    """加密密码"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def get_current_user(token: str) -> Optional[dict]:
    """根据token获取当前用户，检查 token 是否过期"""
    if token and token in active_tokens:
        user_data = active_tokens[token]
        login_time = datetime.fromisoformat(user_data["login_time"])
        if (datetime.now() - login_time).total_seconds() > TOKEN_TTL_SECONDS:
            del active_tokens[token]
            return None
        return user_data
    return None


async def require_auth(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """验证用户登录（依赖项）"""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    user = get_current_user(token)
    if not user:
        raise HTTPException(401, detail="未登录或登录已过期")
    return user


async def require_admin(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """验证管理员权限（依赖项）"""
    user = await require_auth(request, db)
    if user.get("role") != "admin":
        raise HTTPException(403, detail="需要管理员权限")
    return user


# ============ 操作日志记录 ============

async def log_operation(
    db: AsyncSession,
    user: dict,
    operation: str,
    target_type: str,
    target_id: int = None,
    target_name: str = None,
    old_value: dict = None,
    new_value: dict = None,
    ip_address: str = None
):
    """记录操作日志"""
    log_entry = OperationLog(
        user_id=user.get("id"),
        username=user.get("username"),
        operation=operation,
        target_type=target_type,
        target_id=target_id,
        target_name=target_name,
        old_value=old_value,
        new_value=new_value,
        ip_address=ip_address
    )
    db.add(log_entry)
    await db.commit()
    logger.info(f"[操作日志] {user.get('username')} {operation} {target_type}:{target_id} - {target_name}")


# ============ API Endpoints ============

@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    data: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """用户登录（含 IP 限流：5次/分钟）"""
    client_ip = request.client.host if request.client else "unknown"

    # 限流检查
    now = datetime.now()
    if client_ip in _login_attempts:
        attempts, first_time = _login_attempts[client_ip]
        elapsed = (now - first_time).total_seconds()
        if elapsed > LOGIN_WINDOW_SECONDS:
            _login_attempts.pop(client_ip, None)
        elif attempts >= LOGIN_MAX_ATTEMPTS:
            logger.warning(f"[登录] IP {client_ip} 触发限流（{attempts}次失败）")
            return LoginResponse(success=False, message="登录尝试过于频繁，请1分钟后重试")

    logger.info(f"[登录] 尝试登录: {data.username} from {client_ip}")

    result = await db.execute(
        select(AdminUser).where(AdminUser.username == data.username)
    )
    user = result.scalar_one_or_none()

    if not user:
        logger.warning(f"[登录] 用户不存在: {data.username} from {client_ip}")
        if client_ip in _login_attempts:
            attempts, first_time = _login_attempts[client_ip]
            _login_attempts[client_ip] = (attempts + 1, first_time)
        else:
            _login_attempts[client_ip] = (1, now)
        return LoginResponse(success=False, message="用户名或密码错误")

    if not user.is_active:
        logger.warning(f"[登录] 账户已禁用: {data.username}")
        return LoginResponse(success=False, message="账户已被禁用")

    if not verify_password(data.password, user.password_hash):
        logger.warning(f"[登录] 密码错误: {data.username} from {client_ip}")
        # 记录失败次数
        if client_ip in _login_attempts:
            attempts, first_time = _login_attempts[client_ip]
            _login_attempts[client_ip] = (attempts + 1, first_time)
        else:
            _login_attempts[client_ip] = (1, now)
        return LoginResponse(success=False, message="用户名或密码错误")

    # 登录成功，清除限流记录
    _login_attempts.pop(client_ip, None)

    # 生成token
    token = secrets.token_urlsafe(32)
    active_tokens[token] = {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "login_time": datetime.now().isoformat()
    }

    # 更新最后登录时间
    user.last_login = datetime.now()
    await db.commit()

    # 记录登录日志
    await log_operation(
        db, active_tokens[token], "login", "user",
        target_id=user.id,
        target_name=user.username,
        ip_address=request.client.host if request.client else None
    )

    logger.info(f"[登录] 登录成功: {data.username}")
    return LoginResponse(
        success=True,
        token=token,
        user={
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role
        }
    )


@router.post("/logout")
async def logout(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """用户登出"""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    user = get_current_user(token)

    if user and token in active_tokens:
        await log_operation(
            db, user, "logout", "user",
            target_id=user.get("id"),
            target_name=user.get("username"),
            ip_address=request.client.host if request.client else None
        )
        del active_tokens[token]
        logger.info(f"[登出] {user.get('username')}")

    return {"success": True}


@router.get("/me")
async def get_current_user_info(
    user: dict = Depends(require_auth)
):
    """获取当前用户信息"""
    return {"success": True, "user": user}


@router.post("/change-password")
async def change_password(
    request: Request,
    data: ChangePasswordRequest,
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db)
):
    """修改密码"""
    result = await db.execute(
        select(AdminUser).where(AdminUser.id == user["id"])
    )
    db_user = result.scalar_one_or_none()

    if not db_user:
        raise HTTPException(404, detail="用户不存在")

    if not verify_password(data.old_password, db_user.password_hash):
        raise HTTPException(400, detail="原密码错误")

    db_user.password_hash = hash_password(data.new_password)
    await db.commit()

    await log_operation(
        db, user, "change_password", "user",
        target_id=user["id"],
        target_name=user["username"],
        ip_address=request.client.host if request.client else None
    )

    logger.info(f"[修改密码] {user['username']}")
    return {"success": True, "message": "密码修改成功"}


# ============ 用户管理（仅管理员） ============

@router.get("/users")
async def list_users(
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取用户列表"""
    result = await db.execute(
        select(AdminUser).order_by(AdminUser.id)
    )
    users = result.scalars().all()

    return {
        "success": True,
        "users": [{
            "id": u.id,
            "username": u.username,
            "display_name": u.display_name,
            "role": u.role,
            "is_active": u.is_active,
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "created_at": u.created_at.isoformat() if u.created_at else None
        } for u in users]
    }


@router.post("/users")
async def create_user(
    request: Request,
    data: UserCreate,
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """创建用户"""
    # 检查用户名是否已存在
    result = await db.execute(
        select(AdminUser).where(AdminUser.username == data.username)
    )
    if result.scalar_one_or_none():
        raise HTTPException(400, detail="用户名已存在")

    new_user = AdminUser(
        username=data.username,
        password_hash=hash_password(data.password),
        display_name=data.display_name or data.username,
        role=data.role
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    await log_operation(
        db, admin, "create", "user",
        target_id=new_user.id,
        target_name=new_user.username,
        new_value={"username": data.username, "role": data.role},
        ip_address=request.client.host if request.client else None
    )

    logger.info(f"[创建用户] {admin['username']} 创建了 {data.username}")
    return {"success": True, "id": new_user.id, "message": "用户创建成功"}


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    request: Request,
    data: UserUpdate,
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """更新用户"""
    result = await db.execute(
        select(AdminUser).where(AdminUser.id == user_id)
    )
    db_user = result.scalar_one_or_none()

    if not db_user:
        raise HTTPException(404, detail="用户不存在")

    old_value = {
        "display_name": db_user.display_name,
        "role": db_user.role,
        "is_active": db_user.is_active
    }

    if data.display_name is not None:
        db_user.display_name = data.display_name
    if data.role is not None:
        db_user.role = data.role
    if data.is_active is not None:
        db_user.is_active = data.is_active

    await db.commit()

    await log_operation(
        db, admin, "update", "user",
        target_id=user_id,
        target_name=db_user.username,
        old_value=old_value,
        new_value=data.model_dump(exclude_unset=True),
        ip_address=request.client.host if request.client else None
    )

    logger.info(f"[更新用户] {admin['username']} 更新了 {db_user.username}")
    return {"success": True, "message": "用户更新成功"}


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    request: Request,
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """重置用户密码（管理员操作）"""
    result = await db.execute(
        select(AdminUser).where(AdminUser.id == user_id)
    )
    db_user = result.scalar_one_or_none()

    if not db_user:
        raise HTTPException(404, detail="用户不存在")

    # 生成随机密码
    new_password = generate_random_password()
    db_user.password_hash = hash_password(new_password)
    await db.commit()

    await log_operation(
        db, admin, "reset_password", "user",
        target_id=user_id,
        target_name=db_user.username,
        ip_address=request.client.host if request.client else None
    )

    logger.info(f"[重置密码] {admin['username']} 重置了 {db_user.username} 的密码")
    return {"success": True, "message": "密码已重置，请通知用户使用新密码登录", "temp_password": new_password}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    request: Request,
    admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """删除用户"""
    if user_id == admin["id"]:
        raise HTTPException(400, detail="不能删除自己")

    result = await db.execute(
        select(AdminUser).where(AdminUser.id == user_id)
    )
    db_user = result.scalar_one_or_none()

    if not db_user:
        raise HTTPException(404, detail="用户不存在")

    username = db_user.username
    await db.delete(db_user)
    await db.commit()

    await log_operation(
        db, admin, "delete", "user",
        target_id=user_id,
        target_name=username,
        ip_address=request.client.host if request.client else None
    )

    logger.info(f"[删除用户] {admin['username']} 删除了 {username}")
    return {"success": True, "message": "用户已删除"}


# ============ 操作日志查询 ============

@router.get("/logs")
async def get_operation_logs(
    page: int = 1,
    page_size: int = 50,
    username: str = None,
    operation: str = None,
    target_type: str = None,
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db)
):
    """获取操作日志"""
    query = select(OperationLog)
    count_query = select(func.count(OperationLog.id))

    filters = []
    if username:
        filters.append(OperationLog.username == username)
    if operation:
        filters.append(OperationLog.operation == operation)
    if target_type:
        filters.append(OperationLog.target_type == target_type)

    if filters:
        from sqlalchemy import and_
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))

    # 获取总数
    result = await db.execute(count_query)
    total = result.scalar()

    # 分页查询
    offset = (page - 1) * page_size
    query = query.order_by(desc(OperationLog.created_at)).offset(offset).limit(page_size)

    result = await db.execute(query)
    logs = result.scalars().all()

    return {
        "success": True,
        "logs": [{
            "id": log.id,
            "username": log.username,
            "operation": log.operation,
            "target_type": log.target_type,
            "target_id": log.target_id,
            "target_name": log.target_name,
            "old_value": log.old_value,
            "new_value": log.new_value,
            "ip_address": log.ip_address,
            "created_at": log.created_at.isoformat() if log.created_at else None
        } for log in logs],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }


# ============ 导出供其他模块使用 ============

def get_log_function():
    """返回日志记录函数供其他模块使用"""
    return log_operation


def get_auth_dependency():
    """返回认证依赖项供其他模块使用"""
    return require_auth
