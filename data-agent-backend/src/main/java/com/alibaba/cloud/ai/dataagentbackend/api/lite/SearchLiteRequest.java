package com.alibaba.cloud.ai.dataagentbackend.api.lite;

public record SearchLiteRequest(String agentId, String threadId, String query, boolean humanReviewEnabled,
		Boolean humanFeedbackApproved, String humanFeedbackComment) {

	public SearchLiteRequest(String agentId, String threadId, String query) {
		this(agentId, threadId, query, false, null, null);
	}

	public boolean hasHumanFeedback() {
		return humanFeedbackApproved != null;
	}
}

