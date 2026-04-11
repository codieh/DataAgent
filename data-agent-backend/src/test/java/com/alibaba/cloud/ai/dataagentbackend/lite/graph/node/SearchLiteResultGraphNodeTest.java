package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStepOutputAdapter;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStepResult;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.impl.ResultMinimaxStep;
import com.alibaba.cloud.ai.graph.OverAllState;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.List;
import java.util.Map;
import java.util.Optional;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.QUERY;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.RESULT_SUMMARY;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.ROWS;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.SQL;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.THREAD_ID;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SearchLiteResultGraphNodeTest {

	@Test
	void should_bridge_graph_state_into_result_step_and_return_summary() {
		ResultMinimaxStep resultStep = mock(ResultMinimaxStep.class);
		SearchLiteGraphStepOutputAdapter outputAdapter = mock(SearchLiteGraphStepOutputAdapter.class);
		OverAllState graphState = mock(OverAllState.class);

		when(graphState.value(any())).thenReturn(Optional.empty());
		when(graphState.value(THREAD_ID)).thenReturn(Optional.of("thread-2"));
		when(graphState.value(QUERY)).thenReturn(Optional.of("查询高消费用户"));
		when(graphState.value(SQL)).thenReturn(Optional.of("select 1"));
		when(graphState.value(ROWS)).thenReturn(Optional.of(List.of(Map.of("id", 1))));

		SearchLiteState updated = new SearchLiteState();
		updated.setThreadId("thread-2");
		updated.setQuery("查询高消费用户");
		updated.setSql("select 1");
		updated.setRows(List.of(Map.of("id", 1)));
		updated.setResultSummary("这是结果总结");

		when(resultStep.run(any(), any()))
			.thenReturn(new SearchLiteStepResult(Flux.empty(), Mono.just(updated)));

		when(outputAdapter.adapt(any(), any())).thenReturn(Map.of(THREAD_ID, "thread-2", QUERY, "查询高消费用户",
				RESULT_SUMMARY, "这是结果总结"));

		SearchLiteResultGraphNode node = new SearchLiteResultGraphNode(List.<SearchLiteStep>of(resultStep), outputAdapter);

		Map<String, Object> result = node.apply(graphState);

		assertEquals("thread-2", result.get(THREAD_ID));
		assertEquals("查询高消费用户", result.get(QUERY));
		assertEquals("这是结果总结", result.get(RESULT_SUMMARY));
	}

}
