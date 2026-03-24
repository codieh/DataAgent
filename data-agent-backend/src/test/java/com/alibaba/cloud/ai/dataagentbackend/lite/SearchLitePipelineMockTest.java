package com.alibaba.cloud.ai.dataagentbackend.lite;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteRequest;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.time.Duration;
import java.util.EnumMap;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/**
 * A 层稳定回归（mock 串测）：不依赖真实 MiniMax/MySQL。
 *
 * <p>
 * 目标：保证 Orchestrator 能把所有阶段串起来，最后一定能输出 RESULT done。
 * </p>
 */
@SpringBootTest(properties = {
		// 使用 H2，避免测试环境依赖本地 MySQL
		"spring.datasource.url=jdbc:h2:mem:testdb;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=true",
		"spring.datasource.driver-class-name=org.h2.Driver",
		"spring.datasource.username=sa",
		"spring.datasource.password=",

		// pipeline 使用 mock provider（稳定、可重复）
		"search.lite.intent.provider=mock",
		"search.lite.evidence.provider=mock",
		"search.lite.schema.introspect.provider=mock",
		"search.lite.enhance.provider=mock",
		"search.lite.sql.generate.provider=mock",
		"search.lite.sql.execute.provider=mock",
		"search.lite.result.provider=mock",

		// 降低日志噪音
		"APP_LOG_LEVEL=INFO"
})
class SearchLitePipelineMockTest {

	@Autowired
	private SearchLiteOrchestrator orchestrator;

	@Test
	void pipeline_should_complete_and_emit_stages_in_order() {
		SearchLiteRequest req = new SearchLiteRequest("agent-1", "thread-1", "查询订单信息");
		List<SearchLiteMessage> msgs = orchestrator.stream(req).collectList().block(Duration.ofSeconds(10));

		assertNotNull(msgs);
		assertFalse(msgs.isEmpty());

		// 至少有一个 done=true 的 RESULT 消息
		assertTrue(msgs.stream().anyMatch(m -> m != null && m.done() && m.stage() == SearchLiteStage.RESULT));

		// 每个 stage 的第一次出现顺序应递增
		EnumMap<SearchLiteStage, Integer> firstIndex = new EnumMap<>(SearchLiteStage.class);
		for (int i = 0; i < msgs.size(); i++) {
			SearchLiteMessage m = msgs.get(i);
			if (m == null) {
				continue;
			}
			firstIndex.putIfAbsent(m.stage(), i);
		}

		assertTrue(firstIndex.containsKey(SearchLiteStage.INTENT));
		assertTrue(firstIndex.containsKey(SearchLiteStage.EVIDENCE));
		assertTrue(firstIndex.containsKey(SearchLiteStage.SCHEMA));
		assertTrue(firstIndex.containsKey(SearchLiteStage.SCHEMA_RECALL));
		assertTrue(firstIndex.containsKey(SearchLiteStage.ENHANCE));
		assertTrue(firstIndex.containsKey(SearchLiteStage.SQL_GENERATE));
		assertTrue(firstIndex.containsKey(SearchLiteStage.SQL_EXECUTE));
		assertTrue(firstIndex.containsKey(SearchLiteStage.RESULT));

		assertTrue(firstIndex.get(SearchLiteStage.INTENT) < firstIndex.get(SearchLiteStage.EVIDENCE));
		assertTrue(firstIndex.get(SearchLiteStage.EVIDENCE) < firstIndex.get(SearchLiteStage.SCHEMA));
		assertTrue(firstIndex.get(SearchLiteStage.SCHEMA) < firstIndex.get(SearchLiteStage.SCHEMA_RECALL));
		assertTrue(firstIndex.get(SearchLiteStage.SCHEMA_RECALL) < firstIndex.get(SearchLiteStage.ENHANCE));
		assertTrue(firstIndex.get(SearchLiteStage.ENHANCE) < firstIndex.get(SearchLiteStage.SQL_GENERATE));
		assertTrue(firstIndex.get(SearchLiteStage.SQL_GENERATE) < firstIndex.get(SearchLiteStage.SQL_EXECUTE));
		assertTrue(firstIndex.get(SearchLiteStage.SQL_EXECUTE) < firstIndex.get(SearchLiteStage.RESULT));
	}

}

