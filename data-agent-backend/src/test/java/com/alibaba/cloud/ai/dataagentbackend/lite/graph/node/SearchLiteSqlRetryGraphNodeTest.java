package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys;
import com.alibaba.cloud.ai.graph.OverAllState;
import org.junit.jupiter.api.Test;

import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SearchLiteSqlRetryGraphNodeTest {

	private final SearchLiteSqlRetryGraphNode node = new SearchLiteSqlRetryGraphNode();

	@Test
	void should_increment_retry_and_clear_error() {
		OverAllState state = mock(OverAllState.class);
		when(state.value(anyString())).thenReturn(Optional.empty());
		when(state.value(SearchLiteGraphStateKeys.SQL_RETRY_COUNT)).thenReturn(Optional.of(0));
		when(state.value(SearchLiteGraphStateKeys.SQL)).thenReturn(Optional.of("select bad"));
		when(state.value(SearchLiteGraphStateKeys.ERROR)).thenReturn(Optional.of("syntax error"));

		var result = node.apply(state);

		assertEquals(1, result.get(SearchLiteGraphStateKeys.SQL_RETRY_COUNT));
		assertEquals("select bad", result.get(SearchLiteGraphStateKeys.LAST_FAILED_SQL));
		assertEquals("syntax error", result.get(SearchLiteGraphStateKeys.SQL_RETRY_REASON));
		assertNull(result.get(SearchLiteGraphStateKeys.ERROR));
	}

}
