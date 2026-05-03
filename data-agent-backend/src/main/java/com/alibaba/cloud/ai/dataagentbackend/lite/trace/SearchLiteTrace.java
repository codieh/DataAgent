package com.alibaba.cloud.ai.dataagentbackend.lite.trace;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

public class SearchLiteTrace {

	private String traceId;

	private String threadId;

	private String agentId;

	private String query;

	private String mode;

	private boolean resumed;

	private Instant startedAt;

	private Instant endedAt;

	private long durationMs;

	private String finalIntentClassification;

	private String finalResultMode;

	private String finalPlanFinishedReason;

	private String finalError;

	private String finishSignal;

	private final List<SearchLiteTraceStep> steps = new ArrayList<>();

	public String getTraceId() {
		return traceId;
	}

	public void setTraceId(String traceId) {
		this.traceId = traceId;
	}

	public String getThreadId() {
		return threadId;
	}

	public void setThreadId(String threadId) {
		this.threadId = threadId;
	}

	public String getAgentId() {
		return agentId;
	}

	public void setAgentId(String agentId) {
		this.agentId = agentId;
	}

	public String getQuery() {
		return query;
	}

	public void setQuery(String query) {
		this.query = query;
	}

	public String getMode() {
		return mode;
	}

	public void setMode(String mode) {
		this.mode = mode;
	}

	public boolean isResumed() {
		return resumed;
	}

	public void setResumed(boolean resumed) {
		this.resumed = resumed;
	}

	public Instant getStartedAt() {
		return startedAt;
	}

	public void setStartedAt(Instant startedAt) {
		this.startedAt = startedAt;
	}

	public Instant getEndedAt() {
		return endedAt;
	}

	public void setEndedAt(Instant endedAt) {
		this.endedAt = endedAt;
	}

	public long getDurationMs() {
		return durationMs;
	}

	public void setDurationMs(long durationMs) {
		this.durationMs = durationMs;
	}

	public String getFinalIntentClassification() {
		return finalIntentClassification;
	}

	public void setFinalIntentClassification(String finalIntentClassification) {
		this.finalIntentClassification = finalIntentClassification;
	}

	public String getFinalResultMode() {
		return finalResultMode;
	}

	public void setFinalResultMode(String finalResultMode) {
		this.finalResultMode = finalResultMode;
	}

	public String getFinalPlanFinishedReason() {
		return finalPlanFinishedReason;
	}

	public void setFinalPlanFinishedReason(String finalPlanFinishedReason) {
		this.finalPlanFinishedReason = finalPlanFinishedReason;
	}

	public String getFinalError() {
		return finalError;
	}

	public void setFinalError(String finalError) {
		this.finalError = finalError;
	}

	public String getFinishSignal() {
		return finishSignal;
	}

	public void setFinishSignal(String finishSignal) {
		this.finishSignal = finishSignal;
	}

	public List<SearchLiteTraceStep> getSteps() {
		return steps;
	}

}
