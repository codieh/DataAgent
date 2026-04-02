package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphMessageEmitter;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStepResult;
import com.alibaba.cloud.ai.graph.OverAllState;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.List;
import java.util.Map;
import java.util.Optional;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.CANONICAL_QUERY;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.EXPANDED_QUERIES;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.QUERY;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.THREAD_ID;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SearchLiteEnhanceGraphNodeTest {

	@Test
	void should_bridge_graph_state_into_enhance_step_and_return_updated_state() {
		SearchLiteStep enhanceStep = mock(SearchLiteStep.class);
		SearchLiteGraphMessageEmitter messageEmitter = mock(SearchLiteGraphMessageEmitter.class);
		OverAllState graphState = mock(OverAllState.class);

		when(enhanceStep.stage()).thenReturn(SearchLiteStage.ENHANCE);
		when(graphState.value(any())).thenReturn(Optional.empty());
		when(graphState.value(THREAD_ID)).thenReturn(Optional.of("thread-6"));
		when(graphState.value(QUERY)).thenReturn(Optional.of("列出高消费用户"));

		SearchLiteState updated = new SearchLiteState();
		updated.setThreadId("thread-6");
		updated.setQuery("列出高消费用户");
		updated.setCanonicalQuery("列出高消费用户，包括用户ID、总消费金额和订单数量");
		updated.setExpandedQueries(List.of("列出高消费用户，包括用户ID、总消费金额和订单数量", "哪些用户的消费金额最高？"));

		when(enhanceStep.run(any(), any())).thenReturn(new SearchLiteStepResult(Flux.empty(), Mono.just(updated)));

		SearchLiteEnhanceGraphNode node = new SearchLiteEnhanceGraphNode(List.of(enhanceStep), messageEmitter);

		Map<String, Object> result = node.apply(graphState);

		assertEquals("thread-6", result.get(THREAD_ID));
		assertEquals("列出高消费用户", result.get(QUERY));
		assertEquals("列出高消费用户，包括用户ID、总消费金额和订单数量", result.get(CANONICAL_QUERY));
		assertEquals(List.of("列出高消费用户，包括用户ID、总消费金额和订单数量", "哪些用户的消费金额最高？"),
				result.get(EXPANDED_QUERIES));
	}

}
