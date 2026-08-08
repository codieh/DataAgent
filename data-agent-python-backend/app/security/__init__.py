"""安全（security）模块的公共出口。

集中导出两类输入安全护栏：
- 提示注入检测（prompt_injection）：拦截试图改写系统规则或窃取内部信息的用户查询。
- SQL 策略校验（sql_policy）：对生成的 SELECT 语句做白名单 / 禁写 / 敏感字段等约束。

二者均用于在将用户输入或模型产出送入下游（LLM / 数据库）之前进行安全把关。
"""

from app.security.prompt_injection import PromptInjectionGuard, PromptInjectionResult
from app.security.sql_policy import SqlPolicyResult, inspect_select_sql

__all__ = ["PromptInjectionGuard", "PromptInjectionResult", "SqlPolicyResult", "inspect_select_sql"]
