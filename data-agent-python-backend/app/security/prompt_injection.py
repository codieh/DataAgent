"""提示注入（prompt injection）检测。

在把用户查询送入 LLM 之前，基于规则（正则）识别常见注入意图：试图覆盖/忽略系统
指令、索取系统提示词或密钥、要求关闭安全限制、越狱模式等。对长度也做上限约束，
防止超长输入消耗资源或绕过检测。

匹配前先做 NFKC 归一化，抵御全角/特殊字符绕写（如把「忽略」伪装成变体字符）。
"""

import re
import unicodedata
from dataclasses import dataclass


# 注入模式库：覆盖中英文常见指令改写 / 信息窃取 / 越狱意图
_INJECTION_PATTERNS = (
    # 中文：要求忽略/绕过之前的系统规则
    re.compile(r"(?:忽略|无视|绕过|覆盖).{0,16}(?:之前|以上|先前|系统|开发者|安全|规则|指令|限制)", re.I),
    # 中文：要求输出/泄露系统提示词或密钥
    re.compile(r"(?:输出|显示|打印|泄露|告诉我|返回).{0,20}(?:系统提示词|开发者指令|内部指令|api\s*key|密钥|环境变量)", re.I),
    # 中文：要求取消/禁用安全校验与限制
    re.compile(r"(?:不要|取消|绕过|禁用|移除).{0,12}(?:limit|限制|校验|审核|安全策略)", re.I),
    # 英文：ignore previous/system/developer instructions
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior|system|developer)\s+(?:instructions?|prompts?|rules?)", re.I),
    # 英文：reveal/leak system prompt or secret
    re.compile(r"(?:reveal|print|show|leak|repeat).{0,20}(?:system\s+prompt|developer\s+message|api\s*key|secret)", re.I),
    # 越狱关键词
    re.compile(r"(?:jailbreak|developer\s+mode|dan\s+mode|越狱模式)", re.I),
    # 中文：要求扮演/切换为不受约束角色
    re.compile(r"(?:你现在是|扮演|切换为).{0,16}(?:系统|开发者|管理员|无约束|不受限制)", re.I),
)


@dataclass(frozen=True)
class PromptInjectionResult:
    """提示注入检测结果。"""

    blocked: bool
    reason: str = ""


class PromptInjectionGuard:
    """基于规则的用户查询注入护栏。"""

    def __init__(self, max_query_chars: int):
        """初始化守卫。

        Args:
            max_query_chars: 允许的最大查询字符数（超过即拦截）。
        """
        self.max_query_chars = max_query_chars

    def inspect(self, query: str) -> PromptInjectionResult:
        """检测 query 是否含注入意图或超限。

        Args:
            query: 待检测的用户查询。

        Returns:
            PromptInjectionResult：blocked 为 True 时 reason 给出拦截原因。
        """
        # NFKC 归一化把全角/兼容字符折叠为标准形式，消解字符伪装绕过
        normalized = unicodedata.normalize("NFKC", query or "").strip()
        if not normalized:
            return PromptInjectionResult(True, "请求内容为空")
        if len(normalized) > self.max_query_chars:
            return PromptInjectionResult(True, "请求内容超过安全长度限制")
        if any(pattern.search(normalized) for pattern in _INJECTION_PATTERNS):
            return PromptInjectionResult(True, "检测到试图修改系统规则或获取内部信息的指令")
        return PromptInjectionResult(False)
