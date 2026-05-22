# -*- coding: utf-8 -*-
"""
统一异常处理模块
定义项目中使用的所有自定义异常类
"""
from typing import Optional, Any, Dict


class BiologyAnalyzerError(Exception):
    """基础异常类 - 所有自定义异常的父类"""

    def __init__(
        self,
        message: str,
        code: str = "UNKNOWN_ERROR",
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，便于API响应"""
        return {
            "error": True,
            "code": self.code,
            "message": self.message,
            "details": self.details
        }


# ============ 配置相关异常 ============

class ConfigurationError(BiologyAnalyzerError):
    """配置错误 - 缺失或无效的配置"""

    def __init__(self, message: str, config_key: Optional[str] = None):
        super().__init__(
            message=message,
            code="CONFIGURATION_ERROR",
            details={"config_key": config_key} if config_key else {}
        )


class MissingAPIKeyError(ConfigurationError):
    """API密钥缺失"""

    def __init__(self, key_name: str = "LLM_API_KEY"):
        super().__init__(
            message=f"未配置{key_name}环境变量",
            config_key=key_name
        )
        self.code = "MISSING_API_KEY"


# ============ 文件处理异常 ============

class FileProcessingError(BiologyAnalyzerError):
    """文件处理错误"""

    def __init__(self, message: str, filename: Optional[str] = None):
        super().__init__(
            message=message,
            code="FILE_PROCESSING_ERROR",
            details={"filename": filename} if filename else {}
        )


class UnsupportedFileTypeError(FileProcessingError):
    """不支持的文件类型"""

    def __init__(self, filename: str, supported_types: list = None):
        supported = supported_types or ["pdf", "docx"]
        super().__init__(
            message=f"不支持的文件类型: {filename}，支持的类型: {', '.join(supported)}",
            filename=filename
        )
        self.code = "UNSUPPORTED_FILE_TYPE"
        self.details["supported_types"] = supported


class FileTooLargeError(FileProcessingError):
    """文件过大"""

    def __init__(self, filename: str, size_mb: float, max_size_mb: float = 50):
        super().__init__(
            message=f"文件过大: {size_mb:.1f}MB，最大允许: {max_size_mb}MB",
            filename=filename
        )
        self.code = "FILE_TOO_LARGE"
        self.details.update({"size_mb": size_mb, "max_size_mb": max_size_mb})


# ============ 分析相关异常 ============

class AnalysisError(BiologyAnalyzerError):
    """分析错误基类"""

    def __init__(self, message: str, question_id: Optional[int] = None):
        super().__init__(
            message=message,
            code="ANALYSIS_ERROR",
            details={"question_id": question_id} if question_id else {}
        )


class QuestionSplitError(AnalysisError):
    """题目拆分失败"""

    def __init__(self, message: str = "题目拆分失败"):
        super().__init__(message=message)
        self.code = "QUESTION_SPLIT_ERROR"


class DifficultyAnalysisError(AnalysisError):
    """难度分析失败"""

    def __init__(self, message: str, question_id: Optional[int] = None):
        super().__init__(message=message, question_id=question_id)
        self.code = "DIFFICULTY_ANALYSIS_ERROR"


class CompetencyAnalysisError(AnalysisError):
    """素养分析失败"""

    def __init__(self, message: str, question_id: Optional[int] = None):
        super().__init__(message=message, question_id=question_id)
        self.code = "COMPETENCY_ANALYSIS_ERROR"


# ============ API相关异常 ============

class APIError(BiologyAnalyzerError):
    """外部API调用错误"""

    def __init__(
        self,
        message: str,
        api_name: str = "unknown",
        status_code: Optional[int] = None
    ):
        super().__init__(
            message=message,
            code="API_ERROR",
            details={"api_name": api_name, "status_code": status_code}
        )


class LLMAPIError(APIError):
    """LLM API错误"""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(
            message=message,
            api_name="LLM",
            status_code=status_code
        )
        self.code = "LLM_API_ERROR"


class RateLimitError(APIError):
    """API限流错误"""

    def __init__(self, api_name: str = "LLM", retry_after: Optional[int] = None):
        super().__init__(
            message=f"{api_name} API请求过于频繁，请稍后重试",
            api_name=api_name,
            status_code=429
        )
        self.code = "RATE_LIMIT_ERROR"
        if retry_after:
            self.details["retry_after"] = retry_after


# ============ 数据库异常 ============

class DatabaseError(BiologyAnalyzerError):
    """数据库错误"""

    def __init__(self, message: str, operation: Optional[str] = None):
        super().__init__(
            message=message,
            code="DATABASE_ERROR",
            details={"operation": operation} if operation else {}
        )


class RecordNotFoundError(DatabaseError):
    """记录不存在"""

    def __init__(self, entity: str, entity_id: Any):
        super().__init__(
            message=f"{entity}不存在: {entity_id}",
            operation="query"
        )
        self.code = "RECORD_NOT_FOUND"
        self.details.update({"entity": entity, "entity_id": entity_id})


class DuplicateRecordError(DatabaseError):
    """记录重复"""

    def __init__(self, entity: str, field: str, value: Any):
        super().__init__(
            message=f"{entity}已存在: {field}={value}",
            operation="insert"
        )
        self.code = "DUPLICATE_RECORD"
        self.details.update({"entity": entity, "field": field, "value": value})


# ============ 认证异常 ============

class AuthenticationError(BiologyAnalyzerError):
    """认证错误"""

    def __init__(self, message: str = "认证失败"):
        super().__init__(
            message=message,
            code="AUTHENTICATION_ERROR"
        )


class InvalidCredentialsError(AuthenticationError):
    """凭证无效"""

    def __init__(self):
        super().__init__(message="用户名或密码错误")
        self.code = "INVALID_CREDENTIALS"


class TokenExpiredError(AuthenticationError):
    """Token过期"""

    def __init__(self):
        super().__init__(message="登录已过期，请重新登录")
        self.code = "TOKEN_EXPIRED"


class InsufficientPermissionError(AuthenticationError):
    """权限不足"""

    def __init__(self, required_role: str = "admin"):
        super().__init__(message=f"权限不足，需要{required_role}角色")
        self.code = "INSUFFICIENT_PERMISSION"
        self.details["required_role"] = required_role


# ============ 输入验证异常 ============

class ValidationError(BiologyAnalyzerError):
    """输入验证错误"""

    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            details={"field": field} if field else {}
        )


class InvalidParameterError(ValidationError):
    """参数无效"""

    def __init__(self, param_name: str, value: Any, expected: str):
        super().__init__(
            message=f"参数{param_name}无效: {value}，期望: {expected}",
            field=param_name
        )
        self.code = "INVALID_PARAMETER"
        self.details.update({"value": str(value), "expected": expected})
