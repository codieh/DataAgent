"""token 估算与截断工具。

由于本项目提示词混合中英文，这里采用与主流分词器近似的启发式估算：
- 非 ASCII 字符（多为中文等）按 1 token/字 计。
- ASCII 字符（英文/数字/符号）按 4 字符≈1 token 计。
该估算用于上下文窗口预算控制，不追求与具体模型 tokenizer 完全一致。
"""

def estimate_tokens(text: str) -> int:
    """对混合中英文文本做保守的 token 数估算。

    中文等非 ASCII 字符按 1 个 token 计，ASCII 字符每 4 个约 1 个 token。
    结果至少为 1，避免空文本被计为 0。
    """
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    non_ascii_chars = len(text) - ascii_chars
    return max(1, ascii_chars // 4 + non_ascii_chars)


def truncate_to_tokens(text: str, budget: int) -> str:
    """按 token 预算从文本开头截断，保留尽可能多的前缀内容。

    参数:
        text: 待截断文本。
        budget: 允许保留的最大 token 数。
    返回:
        预算内的最长前缀（已去除右侧空白）；若原文不超预算则原样返回。
    """
    # 未超预算直接返回，避免无谓遍历。
    if estimate_tokens(text) <= budget:
        return text
    selected = []
    used = 0.0
    for char in text:
        # 与 estimate_tokens 一致的单字符成本：非 ASCII 计 1，ASCII 计 0.25。
        cost = 1.0 if ord(char) >= 128 else 0.25
        if used + cost > budget:
            break
        selected.append(char)
        used += cost
    # 去除右侧空白，避免截断点落在纯空格处。
    return "".join(selected).rstrip()
