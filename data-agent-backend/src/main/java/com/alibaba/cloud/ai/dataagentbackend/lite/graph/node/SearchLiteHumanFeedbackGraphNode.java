package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessageType;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLitePlanStep;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteMessages;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphMessageEmitter;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateMapper;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.NodeAction;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

@Component
public class SearchLiteHumanFeedbackGraphNode implements NodeAction {

	private static final Logger log = LoggerFactory.getLogger(SearchLiteHumanFeedbackGraphNode.class);

	private final SearchLiteGraphMessageEmitter messageEmitter;

	private final int maxRepairAttempts;

	public SearchLiteHumanFeedbackGraphNode(SearchLiteGraphMessageEmitter messageEmitter,
			@Value("${search.lite.graph.planner.max-repair-attempts:2}") int maxRepairAttempts) {
		this.messageEmitter = Objects.requireNonNull(messageEmitter, "messageEmitter");
		this.maxRepairAttempts = Math.max(0, maxRepairAttempts);
	}

	@Override
	public Map<String, Object> apply(OverAllState state) {
		SearchLiteState liteState = SearchLiteGraphStateMapper.toSearchLiteState(state);
		SearchLiteContext context = new SearchLiteContext(resolveThreadId(liteState));

		String feedbackStatus = safe(liteState.getHumanFeedbackStatus()).toUpperCase();
		if (!StringUtils.hasText(feedbackStatus)) {
			liteState.setAwaitingHumanFeedback(true);
			liteState.setPlanFinished(true);
			liteState.setPlanFinishedReason("waiting_human_feedback");
			liteState.setResultMode("waiting_human_feedback");
			emitWaiting(context, liteState);
			log.info("human feedback node waiting: threadId={}, steps={}", context.threadId(),
					liteState.getPlanSteps() == null ? 0 : liteState.getPlanSteps().size());
			return SearchLiteGraphStateMapper.fromSearchLiteState(liteState);
		}

		liteState.setAwaitingHumanFeedback(false);
		liteState.setPlanFinished(false);
		liteState.setPlanFinishedReason(null);
		liteState.setResultMode(null);

		if ("APPROVED".equalsIgnoreCase(feedbackStatus)) {
			liteState.setHumanReviewEnabled(false);
			emitApproved(context, liteState);
			log.info("human feedback approved: threadId={}", context.threadId());
			return SearchLiteGraphStateMapper.fromSearchLiteState(liteState);
		}

		if ("REJECTED".equalsIgnoreCase(feedbackStatus)) {
			liteState.setHumanReviewEnabled(true);
			liteState.setPlanValidationStatus(false);
			liteState.setPlanValidationError(StringUtils.hasText(liteState.getHumanFeedbackComment())
					? liteState.getHumanFeedbackComment().trim()
					: "Plan rejected by human reviewer");
			liteState.setPlanRepairCount(liteState.getPlanRepairCount() + 1);
			liteState.setPlannerRawOutput("");
			liteState.setCurrentPlanStepIndex(0);
			resetPlanSteps(liteState.getPlanSteps());
			if (liteState.getPlanRepairCount() > maxRepairAttempts) {
				liteState.setPlanFinished(true);
				liteState.setPlanFinishedReason("human_feedback_repair_exhausted");
				liteState.setResultMode("execution_error");
				liteState.setError("人工反馈驳回次数超过上限：" + liteState.getPlanValidationError());
			}
			emitRejected(context, liteState);
			log.info("human feedback rejected: threadId={}, repairCount={}, comment={}", context.threadId(),
					liteState.getPlanRepairCount(), liteState.getPlanValidationError());
			return SearchLiteGraphStateMapper.fromSearchLiteState(liteState);
		}

		liteState.setAwaitingHumanFeedback(true);
		liteState.setPlanFinished(true);
		liteState.setPlanFinishedReason("waiting_human_feedback");
		liteState.setResultMode("waiting_human_feedback");
		emitWaiting(context, liteState);
		return SearchLiteGraphStateMapper.fromSearchLiteState(liteState);
	}

	private void emitWaiting(SearchLiteContext context, SearchLiteState state) {
		messageEmitter.emitOne(context.threadId(), SearchLiteMessages.message(context, SearchLiteStage.HUMAN_FEEDBACK,
				SearchLiteMessageType.TEXT, "计划已生成，等待人工审核。", null));
		messageEmitter.emitOne(context.threadId(), SearchLiteMessages.done(context, SearchLiteStage.HUMAN_FEEDBACK,
				SearchLiteMessageType.JSON, null,
				Map.of("status", "WAITING", "steps", state.getPlanSteps() == null ? List.of() : state.getPlanSteps(),
						"message", "请基于 threadId 提交人工审核结果后继续执行。")));
	}

	private void emitApproved(SearchLiteContext context, SearchLiteState state) {
		messageEmitter.emitOne(context.threadId(), SearchLiteMessages.done(context, SearchLiteStage.HUMAN_FEEDBACK,
				SearchLiteMessageType.JSON, null,
				Map.of("status", "APPROVED", "message", "人工审核已通过，继续执行计划。")));
	}

	private void emitRejected(SearchLiteContext context, SearchLiteState state) {
		messageEmitter.emitOne(context.threadId(), SearchLiteMessages.done(context, SearchLiteStage.HUMAN_FEEDBACK,
				SearchLiteMessageType.JSON, null,
				Map.of("status", "REJECTED", "repairCount", state.getPlanRepairCount(), "comment",
						safe(state.getPlanValidationError()), "message", "人工审核已拒绝，准备重新规划。")));
	}

	private void resetPlanSteps(List<SearchLitePlanStep> steps) {
		if (steps == null) {
			return;
		}
		for (SearchLitePlanStep step : steps) {
			if (step == null) {
				continue;
			}
			step.setStatus("PENDING");
			step.setSql(null);
			step.setRowCount(0);
			step.setPreviewRows(List.of());
			step.setError(null);
			step.setSummarySnippet(null);
		}
	}

	private String resolveThreadId(SearchLiteState state) {
		if (StringUtils.hasText(state.getThreadId())) {
			return state.getThreadId();
		}
		String generated = "graph-human-feedback-" + UUID.randomUUID();
		state.setThreadId(generated);
		return generated;
	}

	private String safe(String value) {
		return value == null ? "" : value.trim();
	}

}
