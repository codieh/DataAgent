package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaTable;
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
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.SCHEMA_TABLES;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.SCHEMA_TEXT;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.THREAD_ID;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SearchLiteSchemaGraphNodeTest {

	@Test
	void should_bridge_graph_state_into_schema_step_and_return_updated_state() {
		SearchLiteStep schemaStep = mock(SearchLiteStep.class);
		SearchLiteGraphStepOutputAdapter outputAdapter = mock(SearchLiteGraphStepOutputAdapter.class);
		OverAllState graphState = mock(OverAllState.class);

		when(schemaStep.stage()).thenReturn(SearchLiteStage.SCHEMA);
		when(graphState.value(any())).thenReturn(Optional.empty());
		when(graphState.value(THREAD_ID)).thenReturn(Optional.of("thread-4"));
		when(graphState.value(QUERY)).thenReturn(Optional.of("查询高消费用户"));

		SearchLiteState updated = new SearchLiteState();
		updated.setThreadId("thread-4");
		updated.setQuery("查询高消费用户");
		updated.setSchemaTables(List.of("users", "orders"));
		updated.setSchemaTableDetails(List.of(new SchemaTable("users", "用户表", List.of(), List.of())));
		updated.setSchemaText("TABLE users\nTABLE orders");

		when(schemaStep.run(any(), any())).thenReturn(new SearchLiteStepResult(Flux.empty(), Mono.just(updated)));

		when(outputAdapter.adapt(any(), any())).thenReturn(Map.of(THREAD_ID, "thread-4", QUERY, "查询高消费用户",
				SCHEMA_TABLES, List.of("users", "orders"), SCHEMA_TEXT, "TABLE users\nTABLE orders"));

		SearchLiteSchemaGraphNode node = new SearchLiteSchemaGraphNode(List.of(schemaStep), outputAdapter);

		Map<String, Object> result = node.apply(graphState);

		assertEquals("thread-4", result.get(THREAD_ID));
		assertEquals("查询高消费用户", result.get(QUERY));
		assertEquals(List.of("users", "orders"), result.get(SCHEMA_TABLES));
		assertEquals("TABLE users\nTABLE orders", result.get(SCHEMA_TEXT));
	}

}
