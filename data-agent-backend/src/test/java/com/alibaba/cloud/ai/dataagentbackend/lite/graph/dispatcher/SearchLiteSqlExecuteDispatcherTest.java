package com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher;

import com.alibaba.cloud.ai.graph.OverAllState;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Optional;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.RESULT_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.ERROR;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.ROWS;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SearchLiteSqlExecuteDispatcherTest {

	private final SearchLiteSqlExecuteDispatcher dispatcher = new SearchLiteSqlExecuteDispatcher();

	@Test
	void should_route_failed_execution_to_result() {
		OverAllState state = mock(OverAllState.class);
		when(state.value(anyString())).thenReturn(Optional.empty());
		when(state.value(ERROR)).thenReturn(Optional.of("syntax error"));

		assertEquals(RESULT_NODE, dispatcher.apply(state));
	}

	@Test
	void should_route_success_execution_to_result() {
		OverAllState state = mock(OverAllState.class);
		when(state.value(anyString())).thenReturn(Optional.empty());
		when(state.value(ERROR)).thenReturn(Optional.of(""));
		when(state.value(ROWS)).thenReturn(Optional.of(List.of(List.of("ok"))));

		assertEquals(RESULT_NODE, dispatcher.apply(state));
	}

}
