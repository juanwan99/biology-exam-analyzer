"""
数据库连接和会话管理
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
from logger import get_logger

logger = get_logger()

# 数据库URL - 必须通过环境变量配置
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # 仅在开发环境使用默认值
    if os.getenv("ENV", "development") == "development":
        DATABASE_URL = "postgresql://biology:biology123@postgres:5432/biology_edu"
        logger.warning("使用默认数据库连接（仅限开发环境）")
    else:
        raise ValueError("生产环境必须设置 DATABASE_URL 环境变量")
# 转换为异步URL
ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

# 创建异步引擎
engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=False,  # 设为True可以看到SQL语句
    pool_size=10,
    max_overflow=10,
    pool_pre_ping=True,
)

# 创建异步会话工厂
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# 基类
Base = declarative_base()


async def get_db() -> AsyncSession:
    """获取数据库会话（用于依赖注入）"""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """初始化数据库连接（启动时调用）"""
    try:
        async with engine.begin() as conn:
            # 测试连接
            await conn.execute(text("SELECT 1"))
        logger.info("[数据库] 连接成功")
    except Exception as e:
        logger.error(f"[数据库] 连接失败: {e}")
        raise


async def get_db_session() -> AsyncSession:
    """获取数据库会话（直接使用，非依赖注入）"""
    return async_session()
