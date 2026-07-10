"""领域状态枚举。

集中定义运行（Run）、阶段（Stage）、审核（Review）三者的状态集合，并使用
StrEnum 使存储值与枚举成员同名，便于与数据库的字符串状态字段直接映射。
TERMINAL_RUN_STATUSES 描述运行的终态（已结束、不再变化）。
"""

from enum import StrEnum


class RunStatus(StrEnum):
    """一次分析运行的整体状态。"""

    QUEUED = "queued"  # 已创建，尚未开始执行
    RUNNING = "running"  # 正在执行
    WAITING_REVIEW = "waiting_review"  # 已生成计划/SQL，等待人工审核
    COMPLETED = "completed"  # 成功完成
    FAILED = "failed"  # 执行失败
    CANCELLED = "cancelled"  # 被用户/系统取消


class StageStatus(StrEnum):
    """运行内部单个阶段（节点）的状态。"""

    PENDING = "pending"  # 待执行
    RUNNING = "running"  # 执行中
    COMPLETED = "completed"  # 完成
    FAILED = "failed"  # 失败
    SKIPPED = "skipped"  # 被跳过


class ReviewStatus(StrEnum):
    """人工审核记录的状态。"""

    WAITING = "waiting"  # 等待处理
    APPROVED = "approved"  # 已批准
    REJECTED = "rejected"  # 已驳回
    EXPIRED = "expired"  # 已过期（如超时未处理）


# 运行的终态集合：处于这些状态后运行不再向前推进，可用于幂等/取消判断。
TERMINAL_RUN_STATUSES = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}

