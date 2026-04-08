package com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher;

import com.alibaba.cloud.ai.graph.OverAllState;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Optional;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.ENHANCE_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.PREPARE_RESULT_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.RECALLED_TABLES;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SearchLiteSchemaRecallDispatcherTest {

	private final SearchLiteSchemaRecallDispatcher dispatcher = new SearchLiteSchemaRecallDispatcher();

	@Test
	void should_route_to_result_when_no_recalled_tables() {
		OverAllState state = mock(OverAllState.class);
		when(state.value(anyString())).thenReturn(Optional.empty());
		when(state.value(RECALLED_TABLES)).thenReturn(Optional.of(List.of()));

		assertEquals(PREPARE_RESULT_NODE, dispatcher.apply(state));
	}

	@Test
	void should_route_to_enhance_when_recalled_tables_present() {
		OverAllState state = mock(OverAllState.class);
		when(state.value(anyString())).thenReturn(Optional.empty());
		when(state.value(RECALLED_TABLES)).thenReturn(Optional.of(List.of("orders", "order_items")));

		assertEquals(ENHANCE_NODE, dispatcher.apply(state));
	}

}
