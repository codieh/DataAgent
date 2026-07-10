"""pytest 全局固件（fixture）与测试环境配置。

本模块在所有测试文件之前被 pytest 加载，负责：
- 指定测试使用的临时 SQLite 数据库路径；
- 通过环境变量注入测试友好的运行时配置（如关闭检索后端延迟、使用 bm25 检索、关闭长期记忆抽取等），
  以保证测试可重复、快速且不与外部服务耦合。
注意：本文件只设置环境，不定义 pytest fixture 函数。
"""

import os
from pathlib import Path


# 测试数据库统一放在 /tmp 下，避免污染项目目录
TEST_DATABASE = Path("/tmp/data-agent-python-backend-test.db")
TEST_DATASET_DIR = Path("/tmp/data-agent-python-backend-test-datasets")
# 使用内存映射的临时 SQLite 数据库作为测试存储
os.environ.setdefault("DATA_AGENT_DATABASE_URL", f"sqlite+aiosqlite:///{TEST_DATABASE}")
os.environ.setdefault("DATA_AGENT_ANALYSIS_DATASET_DIR", str(TEST_DATASET_DIR))
# 将工作流步骤间隔与 SSE 轮询间隔缩短到几乎为 0，避免测试无谓等待
os.environ.setdefault("DATA_AGENT_WORKFLOW_STEP_DELAY_SECONDS", "0.001")
os.environ.setdefault("DATA_AGENT_SSE_POLL_INTERVAL_SECONDS", "0.001")
# 测试统一使用 bm25 检索后端（无需向量数据库依赖）
os.environ.setdefault("DATA_AGENT_RETRIEVAL_BACKEND", "bm25")
# 关闭长期记忆自动抽取，避免测试中产生额外 LLM 调用
os.environ.setdefault("DATA_AGENT_MEMORY_EXTRACTION_ENABLED", "false")
