package com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher;

import com.alibaba.cloud.ai.graph.OverAllState;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Optional;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.PLAN_EXECUTOR_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.PREPARE_RESULT_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.SQL_RETRY_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.ERROR;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.SQL;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.SQL_RETRY_COUNT;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.ROWS;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SearchLiteSqlExecuteDispatcherTest {

	private final SearchLiteSqlExecuteDispatcher dispatcher = new SearchLiteSqlExecuteDispatcher(1);

	@Test
	void should_route_failed_execution_to_retry_when_retry_available() {
		OverAllState state = mock(OverAllState.class);
		when(state.value(anyString())).thenReturn(Optional.empty());
		when(state.value(ERROR)).thenReturn(Optional.of("syntax error"));
		when(state.value(SQL)).thenReturn(Optional.of("select bad"));
		when(state.value(SQL_RETRY_COUNT)).thenReturn(Optional.of(0));

		assertEquals(SQL_RETRY_NODE, dispatcher.apply(state));
	}

	@Test
	void should_route_failed_execution_to_prepare_result_when_retry_exhausted() {
		OverAllState state = mock(OverAllState.class);
		when(state.value(anyString())).thenReturn(Optional.empty());
		when(state.value(ERROR)).thenReturn(Optional.of("syntax error"));
		when(state.value(SQL)).thenReturn(Optional.of("select bad"));
		when(state.value(SQL_RETRY_COUNT)).thenReturn(Optional.of(1));

		assertEquals(PLAN_EXECUTOR_NODE, dispatcher.apply(state));
	}

	@Test
	void should_route_success_execution_to_result() {
		OverAllState state = mock(OverAllState.class);
		when(state.value(anyString())).thenReturn(Optional.empty());
		when(state.value(ERROR)).thenReturn(Optional.of(""));
		when(state.value(ROWS)).thenReturn(Optional.of(List.of(List.of("ok"))));

		assertEquals(PLAN_EXECUTOR_NODE, dispatcher.apply(state));
	}

}
