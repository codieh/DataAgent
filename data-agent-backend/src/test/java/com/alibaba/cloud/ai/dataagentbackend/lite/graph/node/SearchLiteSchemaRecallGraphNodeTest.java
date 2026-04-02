package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStepOutputAdapter;
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
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.RECALLED_SCHEMA_TEXT;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.RECALLED_TABLES;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.THREAD_ID;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SearchLiteSchemaRecallGraphNodeTest {

	@Test
	void should_bridge_graph_state_into_schema_recall_step_and_return_updated_state() {
		SearchLiteStep schemaRecallStep = mock(SearchLiteStep.class);
		SearchLiteGraphStepOutputAdapter outputAdapter = mock(SearchLiteGraphStepOutputAdapter.class);
		OverAllState graphState = mock(OverAllState.class);

		when(schemaRecallStep.stage()).thenReturn(SearchLiteStage.SCHEMA_RECALL);
		when(graphState.value(any())).thenReturn(Optional.empty());
		when(graphState.value(THREAD_ID)).thenReturn(Optional.of("thread-5"));
		when(graphState.value(QUERY)).thenReturn(Optional.of("查询高消费用户"));

		SearchLiteState updated = new SearchLiteState();
		updated.setThreadId("thread-5");
		updated.setQuery("查询高消费用户");
		updated.setRecalledTables(List.of("users", "orders"));
		updated.setRecalledSchemaText("TABLE users\nTABLE orders");

		when(schemaRecallStep.run(any(), any())).thenReturn(new SearchLiteStepResult(Flux.empty(), Mono.just(updated)));

		when(outputAdapter.adapt(any(), any())).thenReturn(Map.of(THREAD_ID, "thread-5", QUERY, "查询高消费用户",
				RECALLED_TABLES, List.of("users", "orders"), RECALLED_SCHEMA_TEXT, "TABLE users\nTABLE orders"));

		SearchLiteSchemaRecallGraphNode node = new SearchLiteSchemaRecallGraphNode(List.of(schemaRecallStep), outputAdapter);

		Map<String, Object> result = node.apply(graphState);

		assertEquals("thread-5", result.get(THREAD_ID));
		assertEquals("查询高消费用户", result.get(QUERY));
		assertEquals(List.of("users", "orders"), result.get(RECALLED_TABLES));
		assertEquals("TABLE users\nTABLE orders", result.get(RECALLED_SCHEMA_TEXT));
	}

}
