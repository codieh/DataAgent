"""框架无关的工作流节点。

本子包包含与 LangGraph 编排细节解耦的节点实现，核心为 ``AnalysisNodes``：
输入安全校验、Agent 决策循环、SQL 安全校验/人工审核/执行，以及最终分析结果的整理。
每个节点接收 ``AnalysisState`` 并返回需要合并进状态的状态增量（dict）。
"""

