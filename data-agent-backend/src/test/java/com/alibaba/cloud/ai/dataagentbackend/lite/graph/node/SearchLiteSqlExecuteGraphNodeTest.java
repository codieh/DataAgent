package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStepResult;
import com.alibaba.cloud.ai.graph.OverAllState;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.List;
import java.util.Map;
import java.util.Optional;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.QUERY;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.ROWS;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.THREAD_ID;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SearchLiteSqlExecuteGraphNodeTest {

	@Test
	void should_bridge_graph_state_into_sql_execute_step_and_return_updated_state() {
		SearchLiteStep sqlExecuteStep = mock(SearchLiteStep.class);
		OverAllState graphState = mock(OverAllState.class);

		when(sqlExecuteStep.stage()).thenReturn(SearchLiteStage.SQL_EXECUTE);
		when(graphState.value(any())).thenReturn(Optional.empty());
		when(graphState.value(THREAD_ID)).thenReturn(Optional.of("thread-8"));
		when(graphState.value(QUERY)).thenReturn(Optional.of("列出高消费用户"));

		SearchLiteState updated = new SearchLiteState();
		updated.setThreadId("thread-8");
		updated.setQuery("列出高消费用户");
		updated.setRows(List.of(Map.of("user_id", 1, "total_spending", 1000)));

		when(sqlExecuteStep.run(any(), any())).thenReturn(new SearchLiteStepResult(Flux.empty(), Mono.just(updated)));

		SearchLiteSqlExecuteGraphNode node = new SearchLiteSqlExecuteGraphNode(List.of(sqlExecuteStep));

		Map<String, Object> result = node.apply(graphState);

		assertEquals("thread-8", result.get(THREAD_ID));
		assertEquals("列出高消费用户", result.get(QUERY));
		assertEquals(List.of(Map.of("user_id", 1, "total_spending", 1000)), result.get(ROWS));
	}

}
