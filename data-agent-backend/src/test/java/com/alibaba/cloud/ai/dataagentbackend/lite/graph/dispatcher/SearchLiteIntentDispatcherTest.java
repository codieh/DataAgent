package com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher;

import com.alibaba.cloud.ai.graph.OverAllState;
import org.junit.jupiter.api.Test;

import java.util.Optional;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.EVIDENCE_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.INTENT_CLASSIFICATION;
import static com.alibaba.cloud.ai.graph.StateGraph.END;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SearchLiteIntentDispatcherTest {

	private final SearchLiteIntentDispatcher dispatcher = new SearchLiteIntentDispatcher();

	@Test
	void should_route_data_analysis_to_evidence_node() {
		OverAllState state = mock(OverAllState.class);
		when(state.value(anyString())).thenReturn(Optional.empty());
		when(state.value(INTENT_CLASSIFICATION)).thenReturn(Optional.of("DATA_ANALYSIS"));

		assertEquals(EVIDENCE_NODE, dispatcher.apply(state));
	}

	@Test
	void should_route_chitchat_to_end() {
		OverAllState state = mock(OverAllState.class);
		when(state.value(anyString())).thenReturn(Optional.empty());
		when(state.value(INTENT_CLASSIFICATION)).thenReturn(Optional.of("CHITCHAT"));

		assertEquals(END, dispatcher.apply(state));
	}

}
