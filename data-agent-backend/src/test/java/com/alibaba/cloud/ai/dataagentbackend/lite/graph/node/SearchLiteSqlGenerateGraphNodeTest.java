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

import java.util.Map;
import java.util.Optional;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.QUERY;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.SQL;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.THREAD_ID;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SearchLiteSqlGenerateGraphNodeTest {

	@Test
	void should_bridge_graph_state_into_sql_generate_step_and_return_updated_state() {
		SearchLiteStep sqlGenerateStep = mock(SearchLiteStep.class);
		SearchLiteGraphMessageEmitter messageEmitter = mock(SearchLiteGraphMessageEmitter.class);
		OverAllState graphState = mock(OverAllState.class);

		when(sqlGenerateStep.stage()).thenReturn(SearchLiteStage.SQL_GENERATE);
		when(graphState.value(any())).thenReturn(Optional.empty());
		when(graphState.value(THREAD_ID)).thenReturn(Optional.of("thread-7"));
		when(graphState.value(QUERY)).thenReturn(Optional.of("列出高消费用户"));

		SearchLiteState updated = new SearchLiteState();
		updated.setThreadId("thread-7");
		updated.setQuery("列出高消费用户");
		updated.setSql("SELECT u.id, SUM(o.total_amount) AS total_spending FROM users u JOIN orders o ON u.id = o.user_id GROUP BY u.id");

		when(sqlGenerateStep.run(any(), any())).thenReturn(new SearchLiteStepResult(Flux.empty(), Mono.just(updated)));

		SearchLiteSqlGenerateGraphNode node = new SearchLiteSqlGenerateGraphNode(java.util.List.of(sqlGenerateStep), messageEmitter);

		Map<String, Object> result = node.apply(graphState);

		assertEquals("thread-7", result.get(THREAD_ID));
		assertEquals("列出高消费用户", result.get(QUERY));
		assertEquals("SELECT u.id, SUM(o.total_amount) AS total_spending FROM users u JOIN orders o ON u.id = o.user_id GROUP BY u.id",
				result.get(SQL));
	}

}
