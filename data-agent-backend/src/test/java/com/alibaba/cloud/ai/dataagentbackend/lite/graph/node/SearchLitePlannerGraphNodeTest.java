package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.llm.anthropic.AnthropicClient;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphMessageEmitter;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphMessageNormalizer;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.alibaba.cloud.ai.graph.OverAllState;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Optional;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.CANONICAL_QUERY;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.PLAN_STEPS;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.PLANNER_ENABLED;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SearchLitePlannerGraphNodeTest {

	@Test
	void should_split_multi_query_into_sql_plan_steps() {
		AnthropicClient anthropicClient = mock(AnthropicClient.class);
		ObjectMapper objectMapper = new ObjectMapper();
		SearchLiteGraphMessageEmitter emitter = new SearchLiteGraphMessageEmitter(
				new SearchLiteGraphMessageNormalizer(objectMapper));
		OverAllState state = mock(OverAllState.class);
		when(state.value(anyString())).thenReturn(Optional.empty());
		when(state.value(CANONICAL_QUERY)).thenReturn(Optional.of("查询销量最高的商品，然后统计这些商品近6个月趋势"));
		when(anthropicClient.createMessage(anyString(), anyString())).thenReturn(reactor.core.publisher.Mono.just("""
				{"steps":[
				  {"step":1,"instruction":"查询销量最高的商品","tool":"SQL"},
				  {"step":2,"instruction":"统计这些商品近6个月趋势","tool":"SQL"}
				]}
				"""));

		SearchLitePlannerGraphNode node = new SearchLitePlannerGraphNode(anthropicClient, objectMapper, emitter, 5);
		var result = node.apply(state);

		assertTrue((Boolean) result.get(PLANNER_ENABLED));
		List<?> steps = (List<?>) result.get(PLAN_STEPS);
		assertEquals(2, steps.size());
	}

}
