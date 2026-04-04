package com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher;

import com.alibaba.cloud.ai.graph.OverAllState;
import org.junit.jupiter.api.Test;

import java.util.Optional;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.RESULT_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.SQL_EXECUTE_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.SQL;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SearchLiteSqlGenerateDispatcherTest {

	private final SearchLiteSqlGenerateDispatcher dispatcher = new SearchLiteSqlGenerateDispatcher();

	@Test
	void should_route_to_sql_execute_when_sql_present() {
		OverAllState state = mock(OverAllState.class);
		when(state.value(anyString())).thenReturn(Optional.empty());
		when(state.value(SQL)).thenReturn(Optional.of("SELECT * FROM orders LIMIT 10"));

		assertEquals(SQL_EXECUTE_NODE, dispatcher.apply(state));
	}

	@Test
	void should_route_to_sql_execute_when_cte_sql_present() {
		OverAllState state = mock(OverAllState.class);
		when(state.value(anyString())).thenReturn(Optional.empty());
		when(state.value(SQL)).thenReturn(Optional.of("WITH ranked AS (SELECT 1) SELECT * FROM ranked"));

		assertEquals(SQL_EXECUTE_NODE, dispatcher.apply(state));
	}

	@Test
	void should_route_to_result_when_sql_empty() {
		OverAllState state = mock(OverAllState.class);
		when(state.value(anyString())).thenReturn(Optional.empty());
		when(state.value(SQL)).thenReturn(Optional.of(""));

		assertEquals(RESULT_NODE, dispatcher.apply(state));
	}
}
