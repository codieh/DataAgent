"""纯工作流定义与节点。

本包定义与具体框架解耦的分析工作流：
- ``state``：工作流在 LangGraph 中流转的全局状态（TypedDict），所有节点共享。
- ``nodes``：框架无关的节点实现（输入安全校验、Agent 决策、SQL 校验/执行、结果整理）。
- ``context_builder``：把持久化状态投影为面向模型的有界上下文（含 token 预算裁剪）。
- ``prompts`` / ``outputs`` / ``ports`` / ``runtime``：提示词模板、结构化输出模型、
  LLM 客户端端口抽象、以及编排运行时。

注意：``graph.py`` 与 ``tools.py`` 由其他模块负责，这里只描述工作流的“纯”部分。
"""

