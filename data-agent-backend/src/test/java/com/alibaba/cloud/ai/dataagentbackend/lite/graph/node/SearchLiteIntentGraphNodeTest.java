package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStepResult;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.impl.IntentMinimaxStep;
import com.alibaba.cloud.ai.graph.OverAllState;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.Map;
import java.util.Optional;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.QUERY;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.THREAD_ID;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SearchLiteIntentGraphNodeTest {

	@Test
	void should_bridge_graph_state_into_intent_step_and_return_updated_state() {
		IntentMinimaxStep intentStep = mock(IntentMinimaxStep.class);
		OverAllState graphState = mock(OverAllState.class);

		when(graphState.value(THREAD_ID)).thenReturn(Optional.of("thread-1"));
		when(graphState.value(QUERY)).thenReturn(Optional.of("查询高消费用户"));
		when(graphState.value(any())).thenReturn(Optional.empty());
		when(graphState.value(THREAD_ID)).thenReturn(Optional.of("thread-1"));
		when(graphState.value(QUERY)).thenReturn(Optional.of("查询高消费用户"));

		SearchLiteState updated = new SearchLiteState();
		updated.setThreadId("thread-1");
		updated.setQuery("查询高消费用户");
		updated.setIntentClassification("DATA_ANALYSIS");

		when(intentStep.run(any(), any()))
			.thenReturn(new SearchLiteStepResult(Flux.empty(), Mono.just(updated)));

		SearchLiteIntentGraphNode node = new SearchLiteIntentGraphNode(intentStep);

		Map<String, Object> result = node.apply(graphState);

		assertEquals("thread-1", result.get(THREAD_ID));
		assertEquals("查询高消费用户", result.get(QUERY));
		assertEquals("DATA_ANALYSIS", result.get("intentClassification"));
	}

}
