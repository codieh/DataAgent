import re
import unicodedata
from dataclasses import dataclass


_INJECTION_PATTERNS = (
    re.compile(r"(?:忽略|无视|绕过|覆盖).{0,16}(?:之前|以上|先前|系统|开发者|安全|规则|指令|限制)", re.I),
    re.compile(r"(?:输出|显示|打印|泄露|告诉我|返回).{0,20}(?:系统提示词|开发者指令|内部指令|api\s*key|密钥|环境变量)", re.I),
    re.compile(r"(?:不要|取消|绕过|禁用|移除).{0,12}(?:limit|限制|校验|审核|安全策略)", re.I),
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior|system|developer)\s+(?:instructions?|prompts?|rules?)", re.I),
    re.compile(r"(?:reveal|print|show|leak|repeat).{0,20}(?:system\s+prompt|developer\s+message|api\s*key|secret)", re.I),
    re.compile(r"(?:jailbreak|developer\s+mode|dan\s+mode|越狱模式)", re.I),
    re.compile(r"(?:你现在是|扮演|切换为).{0,16}(?:系统|开发者|管理员|无约束|不受限制)", re.I),
)


@dataclass(frozen=True)
class PromptInjectionResult:
    blocked: bool
    reason: str = ""


class PromptInjectionGuard:
    def __init__(self, max_query_chars: int):
        self.max_query_chars = max_query_chars

    def inspect(self, query: str) -> PromptInjectionResult:
        normalized = unicodedata.normalize("NFKC", query or "").strip()
        if not normalized:
            return PromptInjectionResult(True, "请求内容为空")
        if len(normalized) > self.max_query_chars:
            return PromptInjectionResult(True, "请求内容超过安全长度限制")
        if any(pattern.search(normalized) for pattern in _INJECTION_PATTERNS):
            return PromptInjectionResult(True, "检测到试图修改系统规则或获取内部信息的指令")
        return PromptInjectionResult(False)
