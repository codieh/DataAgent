package com.alibaba.cloud.ai.dataagentbackend.lite.conversation;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteRequest;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MultiTurnContextManagerTest {

	@Test
	void shouldBuildContextualizedQueryForFollowUpTurn() {
		MultiTurnContextManager manager = new MultiTurnContextManager(10, 240, 3);
		SearchLiteState first = SearchLiteState.fromRequest(new SearchLiteRequest("agent-1", "thread-1", "查询高消费用户"));
		first.setIntentClassification("DATA_ANALYSIS");
		first.setContextualizedQuery("查询高消费用户");
		first.setCanonicalQuery("查询累计消费金额最高的用户");
		first.setResultSummary("返回了高消费用户列表");

		manager.prepareTurn("thread-1", "查询高消费用户");
		manager.finishTurn(first);

		PreparedConversationContext prepared = manager.prepareTurn("thread-1", "这些用户里谁下单最多");

		assertTrue(prepared.multiTurnContext().contains("[最近第1轮详情]"));
		assertTrue(prepared.multiTurnContext().contains("规范化问题: 查询累计消费金额最高的用户"));
		assertTrue(prepared.contextualizedQuery().contains("基于上一轮查询"));
		assertTrue(prepared.contextualizedQuery().contains("这些用户里谁下单最多"));
	}

	@Test
	void shouldTrimHistoryByMaxTurnCount() {
		MultiTurnContextManager manager = new MultiTurnContextManager(2, 240, 3);
		persist(manager, "thread-2", "查询销量最高商品", "查询销量最高的商品");
		persist(manager, "thread-2", "查询销量第二商品", "查询销量第二高的商品");
		persist(manager, "thread-2", "查询销量第三商品", "查询销量第三高的商品");

		String context = manager.buildContext("thread-2");

		assertTrue(context.contains("查询销量第二高的商品"));
		assertTrue(context.contains("查询销量第三高的商品"));
		assertFalse(context.contains("查询销量最高的商品"));
	}

	@Test
	void shouldSummarizeFirstSevenTurnsWhenHistoryReachesTen() {
		MultiTurnContextManager manager = new MultiTurnContextManager(10, 240, 3);
		for (int i = 1; i <= 10; i++) {
			persist(manager, "thread-3", "第" + i + "轮", "第" + i + "轮规范化");
		}

		String context = manager.buildContext("thread-3");

		assertTrue(context.contains("[会话滚动摘要]"));
		assertTrue(context.contains("第1轮规范化"));
		assertTrue(context.contains("第7轮规范化"));
		assertTrue(context.contains("第8轮规范化"));
		assertTrue(context.contains("第10轮规范化"));
		assertFalse(context.contains("[最近第4轮详情]"));
		assertFalse(context.contains("用户问题: 第7轮"));
	}

	private void persist(MultiTurnContextManager manager, String threadId, String query, String canonicalQuery) {
		manager.prepareTurn(threadId, query);
		SearchLiteState state = SearchLiteState.fromRequest(new SearchLiteRequest("agent-1", threadId, query));
		state.setIntentClassification("DATA_ANALYSIS");
		state.setContextualizedQuery(query);
		state.setCanonicalQuery(canonicalQuery);
		state.setResultSummary("ok");
		manager.finishTurn(state);
	}

}
