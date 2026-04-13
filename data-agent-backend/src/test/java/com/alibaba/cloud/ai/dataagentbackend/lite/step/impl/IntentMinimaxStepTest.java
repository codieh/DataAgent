package com.alibaba.cloud.ai.dataagentbackend.lite.step.impl;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class IntentMinimaxStepTest {

	@Test
	void buildIntentPrompt_should_include_conservative_rules_and_context() {
		String prompt = IntentMinimaxStep.buildIntentPrompt("用户: 查一下销售额", "他们呢？");

		assertTrue(prompt.contains("宁放过，不杀错"));
		assertTrue(prompt.contains("【多轮输入】"));
		assertTrue(prompt.contains("用户: 查一下销售额"));
		assertTrue(prompt.contains("<最新>用户输入："));
		assertTrue(prompt.contains("他们呢？"));
		assertTrue(prompt.contains("\"classification\":\"DATA_ANALYSIS|CHITCHAT\""));
	}

	@Test
	void normalizeClassification_should_support_management_style_labels() {
		assertEquals("DATA_ANALYSIS", IntentMinimaxStep.normalizeClassification("《可能的数据分析请求》"));
		assertEquals("CHITCHAT", IntentMinimaxStep.normalizeClassification("《闲聊或无关指令》"));
		assertEquals("DATA_ANALYSIS", IntentMinimaxStep.normalizeClassification("DATA_ANALYSIS"));
		assertEquals("CHITCHAT", IntentMinimaxStep.normalizeClassification("CHITCHAT"));
	}

}
