package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateMapper;
import com.alibaba.cloud.ai.dataagentbackend.lite.trace.SearchLiteTraceRecorder;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.NodeAction;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.util.Map;

@Component
public class SearchLitePrepareResultGraphNode implements NodeAction {

	private static final Logger log = LoggerFactory.getLogger(SearchLitePrepareResultGraphNode.class);

	private final SearchLiteTraceRecorder traceRecorder;

	public SearchLitePrepareResultGraphNode(SearchLiteTraceRecorder traceRecorder) {
		this.traceRecorder = traceRecorder;
	}

	public static final String MODE_SUCCESS = "success";

	public static final String MODE_NO_SCHEMA = "no_schema";

	public static final String MODE_NO_SQL = "no_sql";

	public static final String MODE_EXECUTION_ERROR = "execution_error";

	public static final String MODE_BLOCKED_SENSITIVE_SQL = "blocked_sensitive_sql";

	public static final String MODE_BLOCKED_WIDE_EXPORT = "blocked_wide_export";

	public static final String MODE_WAITING_HUMAN_FEEDBACK = "waiting_human_feedback";

	public static final String MODE_NEED_CLARIFICATION = "need_clarification";

	public static final String MODE_FREE_CHAT = "free_chat";

	@Override
	public Map<String, Object> apply(OverAllState state) {
		SearchLiteState liteState = SearchLiteGraphStateMapper.toSearchLiteState(state);
		SearchLiteState beforeState = SearchLiteGraphStateMapper.toSearchLiteState(state);
		long startedAt = System.nanoTime();
		if (MODE_NEED_CLARIFICATION.equalsIgnoreCase(liteState.getResultMode())) {
			if (!StringUtils.hasText(liteState.getResultSummary())) {
				liteState.setResultSummary(StringUtils.hasText(liteState.getFeasibilityMessage())
						? liteState.getFeasibilityMessage()
						: "当前问题信息不足，无法生成准确查询。请补充更明确的业务对象、指标名称或筛选条件后再试。");
			}
		}
		else if (MODE_FREE_CHAT.equalsIgnoreCase(liteState.getResultMode())) {
			if (!StringUtils.hasText(liteState.getResultSummary())) {
				liteState.setResultSummary(StringUtils.hasText(liteState.getFeasibilityMessage())
						? liteState.getFeasibilityMessage()
						: "当前请求不是数据分析类问题，无法通过数据查询回答。请问您是否有数据分析相关的需求？");
			}
		}
		else if (liteState.isAwaitingHumanFeedback() || MODE_WAITING_HUMAN_FEEDBACK.equalsIgnoreCase(liteState.getResultMode())) {
			liteState.setResultMode(MODE_WAITING_HUMAN_FEEDBACK);
			if (!StringUtils.hasText(liteState.getResultSummary())) {
				liteState.setResultSummary("计划已生成，等待人工审核后继续执行。");
			}
		}
		else if (StringUtils.hasText(liteState.getResultMode()) && liteState.getResultMode().startsWith("blocked_")) {
			if (!StringUtils.hasText(liteState.getResultSummary())) {
				liteState.setResultSummary(resolveBlockedSummary(liteState));
			}
		}
		else if (StringUtils.hasText(liteState.getError())) {
			liteState.setResultMode(MODE_EXECUTION_ERROR);
			if (!StringUtils.hasText(liteState.getResultSummary())) {
				liteState.setResultSummary("SQL 执行失败：" + liteState.getError());
			}
		}
		else if (!hasRecalledTables(liteState)) {
			liteState.setResultMode(MODE_NO_SCHEMA);
			liteState.setError("未找到与当前问题相关的数据表，请补充更明确的业务对象、指标或筛选条件。");
		}
		else if (!StringUtils.hasText(liteState.getSql())) {
			liteState.setResultMode(MODE_NO_SQL);
			liteState.setError("未生成可执行 SQL，请换一种更明确的描述，或拆分问题后重试。");
		}
		else {
			liteState.setResultMode(MODE_SUCCESS);
			liteState.setError(null);
		}
		log.info("graph prepare-result node invoked: mode={}", liteState.getResultMode());
		traceRecorder.recordStage(liteState.getThreadId(), com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage.RESULT,
				"prepare-result", (System.nanoTime() - startedAt) / 1_000_000, beforeState, liteState, liteState.getError());
		return SearchLiteGraphStateMapper.fromSearchLiteState(liteState);
	}

	private String resolveBlockedSummary(SearchLiteState state) {
		String mode = state.getResultMode();
		if (MODE_BLOCKED_SENSITIVE_SQL.equals(mode)) {
			return "当前 SQL 涉及敏感字段查询，已被安全策略拦截。请改为统计口径、聚合结果或去除敏感明细字段后重试。";
		}
		if (MODE_BLOCKED_WIDE_EXPORT.equals(mode)) {
			return "当前 SQL 可能导致大范围明细导出，已被安全策略拦截。请增加明确筛选条件、限制返回范围，或改为统计查询后重试。";
		}
		return "当前 SQL 已被安全策略拦截。";
	}

	private boolean hasRecalledTables(SearchLiteState state) {
		return state.getRecalledTables() != null && !state.getRecalledTables().isEmpty();
	}

}
