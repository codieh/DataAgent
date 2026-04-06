package com.alibaba.cloud.ai.dataagentbackend.lite.conversation;

/**
 * 单轮会话的轻量摘要，供多轮上下文拼装使用。
 */
public record ConversationTurn(String userQuery, String contextualizedQuery, String canonicalQuery, String sql,
		String resultSummary, String intentClassification) {

	public String anchorQuery() {
		if (canonicalQuery != null && !canonicalQuery.isBlank()) {
			return canonicalQuery.trim();
		}
		if (contextualizedQuery != null && !contextualizedQuery.isBlank()) {
			return contextualizedQuery.trim();
		}
		return userQuery == null ? "" : userQuery.trim();
	}

}
