package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLitePlanStep;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphMessageEmitter;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphMessageNormalizer;
import com.alibaba.cloud.ai.dataagentbackend.lite.trace.SearchLiteTraceRecorder;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.Optional;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.AWAITING_HUMAN_FEEDBACK;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.HUMAN_FEEDBACK_COMMENT;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.HUMAN_FEEDBACK_STATUS;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.PLAN_FINISHED;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.PLAN_REPAIR_COUNT;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.PLAN_STEPS;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.PLAN_VALIDATION_STATUS;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.RESULT_MODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.THREAD_ID;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SearchLiteHumanFeedbackGraphNodeTest {

	@Test
	void should_wait_for_feedback_when_not_provided() {
		OverAllState state = mock(OverAllState.class);
		when(state.value(anyString())).thenReturn(Optional.empty());
		when(state.value(THREAD_ID)).thenReturn(Optional.of("thread-human-1"));
		when(state.value(PLAN_STEPS)).thenReturn(Optional.of(List.of(new SearchLitePlanStep(1, "查询销量最高的商品"))));

		Map<String, Object> result = node().apply(state);

		assertEquals(Boolean.TRUE, result.get(AWAITING_HUMAN_FEEDBACK));
		assertEquals(Boolean.TRUE, result.get(PLAN_FINISHED));
		assertEquals("waiting_human_feedback", result.get(RESULT_MODE));
	}

	@Test
	void should_mark_validation_failed_when_feedback_rejected() {
		SearchLitePlanStep step = new SearchLitePlanStep(1, "查询销量最高的商品");
		step.setStatus("DONE");
		step.setSql("select * from t");
		OverAllState state = mock(OverAllState.class);
		when(state.value(anyString())).thenReturn(Optional.empty());
		when(state.value(THREAD_ID)).thenReturn(Optional.of("thread-human-2"));
		when(state.value(PLAN_STEPS)).thenReturn(Optional.of(List.of(step)));
		when(state.value(HUMAN_FEEDBACK_STATUS)).thenReturn(Optional.of("REJECTED"));
		when(state.value(HUMAN_FEEDBACK_COMMENT)).thenReturn(Optional.of("请先限定时间范围"));

		Map<String, Object> result = node().apply(state);

		assertEquals(Boolean.FALSE, result.get(PLAN_VALIDATION_STATUS));
		assertEquals(1, result.get(PLAN_REPAIR_COUNT));
		@SuppressWarnings("unchecked")
		List<SearchLitePlanStep> steps = (List<SearchLitePlanStep>) result.get(PLAN_STEPS);
		assertEquals("PENDING", steps.get(0).getStatus());
		assertTrue(String.valueOf(result.get("planValidationError")).contains("限定时间范围"));
	}

	private SearchLiteHumanFeedbackGraphNode node() {
		return new SearchLiteHumanFeedbackGraphNode(
				new SearchLiteGraphMessageEmitter(new SearchLiteGraphMessageNormalizer(new ObjectMapper())),
				mock(SearchLiteTraceRecorder.class), 2);
	}

}
