package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.EvidenceItem;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStepOutputAdapter;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStepResult;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.impl.EvidenceFileStep;
import com.alibaba.cloud.ai.graph.OverAllState;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.List;
import java.util.Map;
import java.util.Optional;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.DOCUMENT_TEXT;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.EVIDENCE_TEXT;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.EVIDENCES;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.QUERY;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.THREAD_ID;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SearchLiteEvidenceGraphNodeTest {

	@Test
	void should_bridge_graph_state_into_evidence_step_and_return_updated_state() {
		EvidenceFileStep evidenceStep = mock(EvidenceFileStep.class);
		SearchLiteGraphStepOutputAdapter outputAdapter = mock(SearchLiteGraphStepOutputAdapter.class);
		OverAllState graphState = mock(OverAllState.class);

		when(graphState.value(any())).thenReturn(Optional.empty());
		when(graphState.value(THREAD_ID)).thenReturn(Optional.of("thread-3"));
		when(graphState.value(QUERY)).thenReturn(Optional.of("查询高消费用户"));

		SearchLiteState updated = new SearchLiteState();
		updated.setThreadId("thread-3");
		updated.setQuery("查询高消费用户");
		updated.setEvidences(List.of(new EvidenceItem("e1", "高消费用户定义", "按消费金额排名靠前", "doc://1", 0.9,
				Map.of("topic", "user"))));
		updated.setEvidenceText("高消费用户：按消费金额排名靠前");
		updated.setDocumentText("用户分层定义文档");

		when(evidenceStep.run(any(), any()))
			.thenReturn(new SearchLiteStepResult(Flux.empty(), Mono.just(updated)));

		when(outputAdapter.adapt(any(), any())).thenReturn(Map.of(THREAD_ID, "thread-3", QUERY, "查询高消费用户",
				EVIDENCE_TEXT, "高消费用户：按消费金额排名靠前", DOCUMENT_TEXT, "用户分层定义文档", EVIDENCES, updated.getEvidences()));

		SearchLiteEvidenceGraphNode node = new SearchLiteEvidenceGraphNode(List.<SearchLiteStep>of(evidenceStep),
				outputAdapter);

		Map<String, Object> result = node.apply(graphState);

		assertEquals("thread-3", result.get(THREAD_ID));
		assertEquals("查询高消费用户", result.get(QUERY));
		assertEquals("高消费用户：按消费金额排名靠前", result.get(EVIDENCE_TEXT));
		assertEquals("用户分层定义文档", result.get(DOCUMENT_TEXT));
		assertTrue(((List<?>) result.get(EVIDENCES)).size() == 1);
	}

}
