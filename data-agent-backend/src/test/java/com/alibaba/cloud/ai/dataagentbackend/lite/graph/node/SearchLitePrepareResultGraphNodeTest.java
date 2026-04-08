package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys;
import com.alibaba.cloud.ai.graph.OverAllState;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SearchLitePrepareResultGraphNodeTest {

	private final SearchLitePrepareResultGraphNode node = new SearchLitePrepareResultGraphNode();

	@Test
	void should_mark_no_schema_mode_when_no_recalled_tables() {
		OverAllState state = mock(OverAllState.class);
		when(state.value(anyString())).thenReturn(Optional.empty());
		when(state.value(SearchLiteGraphStateKeys.RECALLED_TABLES)).thenReturn(Optional.of(List.of()));

		Map<String, Object> result = node.apply(state);

		assertEquals("no_schema", result.get(SearchLiteGraphStateKeys.RESULT_MODE));
	}

	@Test
	void should_mark_execution_error_mode_when_error_present() {
		OverAllState state = mock(OverAllState.class);
		when(state.value(anyString())).thenReturn(Optional.empty());
		when(state.value(SearchLiteGraphStateKeys.RECALLED_TABLES)).thenReturn(Optional.of(List.of("orders")));
		when(state.value(SearchLiteGraphStateKeys.ERROR)).thenReturn(Optional.of("syntax error"));
		when(state.value(SearchLiteGraphStateKeys.SQL)).thenReturn(Optional.of("select bad"));

		Map<String, Object> result = node.apply(state);

		assertEquals("execution_error", result.get(SearchLiteGraphStateKeys.RESULT_MODE));
	}

}
