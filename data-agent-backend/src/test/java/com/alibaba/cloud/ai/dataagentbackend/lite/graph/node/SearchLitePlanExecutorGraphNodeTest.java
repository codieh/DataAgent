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

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.CURRENT_PLAN_STEP_INDEX;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.ERROR;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.PLAN_FINISHED;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.PLAN_FINISHED_REASON;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.PLAN_REPAIR_COUNT;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.PLAN_STEPS;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.PLAN_VALIDATION_STATUS;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.RESULT_MODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.ROWS;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.SQL;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.THREAD_ID;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SearchLitePlanExecutorGraphNodeTest {

	@Test
	void should_complete_current_step_and_advance_to_next_running_step() {
		SearchLitePlanStep step1 = new SearchLitePlanStep(1, "查询销量最高的商品");
		step1.setStatus("RUNNING");
		SearchLitePlanStep step2 = new SearchLitePlanStep(2, "统计这些商品近6个月趋势");
		step2.setStatus("PENDING");

		OverAllState state = mock(OverAllState.class);
		when(state.value(anyString())).thenReturn(Optional.empty());
		when(state.value(THREAD_ID)).thenReturn(Optional.of("thread-1"));
		when(state.value(PLAN_STEPS)).thenReturn(Optional.of(List.of(step1, step2)));
		when(state.value(CURRENT_PLAN_STEP_INDEX)).thenReturn(Optional.of(0));
		when(state.value(SQL)).thenReturn(Optional.of("select * from products limit 10"));
		when(state.value(ROWS)).thenReturn(Optional.of(List.of(Map.of("product_name", "商品A"))));
		when(state.value(ERROR)).thenReturn(Optional.of(""));
		when(state.value(RESULT_MODE)).thenReturn(Optional.of(""));

		SearchLitePlanExecutorGraphNode node = new SearchLitePlanExecutorGraphNode(emitter(), traceRecorder(), 2);
		Map<String, Object> result = node.apply(state);

		@SuppressWarnings("unchecked")
		List<SearchLitePlanStep> steps = (List<SearchLitePlanStep>) result.get(PLAN_STEPS);
		assertEquals(2, steps.size());
		assertEquals("DONE", steps.get(0).getStatus());
		assertEquals(1, steps.get(0).getRowCount());
		assertTrue(steps.get(0).getSummarySnippet().contains("返回 1 行结果"));
		assertEquals("RUNNING", steps.get(1).getStatus());
		assertEquals(1, result.get(CURRENT_PLAN_STEP_INDEX));
		assertEquals(Boolean.FALSE, result.get(PLAN_FINISHED));
	}

	@Test
	void should_finish_when_validation_fails_and_repair_is_exhausted() {
		SearchLitePlanStep invalid = new SearchLitePlanStep(1, "查询");
		invalid.setTool("PYTHON");

		OverAllState state = mock(OverAllState.class);
		when(state.value(anyString())).thenReturn(Optional.empty());
		when(state.value(THREAD_ID)).thenReturn(Optional.of("thread-2"));
		when(state.value(PLAN_STEPS)).thenReturn(Optional.of(List.of(invalid)));
		when(state.value(CURRENT_PLAN_STEP_INDEX)).thenReturn(Optional.of(0));
		when(state.value(PLAN_REPAIR_COUNT)).thenReturn(Optional.of(0));

		SearchLitePlanExecutorGraphNode node = new SearchLitePlanExecutorGraphNode(emitter(), traceRecorder(), 0);
		Map<String, Object> result = node.apply(state);

		assertEquals(Boolean.FALSE, result.get(PLAN_VALIDATION_STATUS));
		assertEquals(Boolean.TRUE, result.get(PLAN_FINISHED));
		assertEquals("repair_exhausted", result.get(PLAN_FINISHED_REASON));
		assertTrue(String.valueOf(result.get(ERROR)).contains("计划生成失败"));
	}

	private SearchLiteGraphMessageEmitter emitter() {
		return new SearchLiteGraphMessageEmitter(new SearchLiteGraphMessageNormalizer(new ObjectMapper()));
	}

	private SearchLiteTraceRecorder traceRecorder() {
		return mock(SearchLiteTraceRecorder.class);
	}

}
