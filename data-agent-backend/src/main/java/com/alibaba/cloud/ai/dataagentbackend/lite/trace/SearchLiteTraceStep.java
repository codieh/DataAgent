package com.alibaba.cloud.ai.dataagentbackend.lite.trace;

import java.time.Instant;
import java.util.Map;

public class SearchLiteTraceStep {

	private String stage;

	private String route;

	private Instant startedAt;

	private Instant endedAt;

	private long durationMs;

	private Map<String, Object> inputSummary;

	private Map<String, Object> outputSummary;

	private String error;

	public String getStage() {
		return stage;
	}

	public void setStage(String stage) {
		this.stage = stage;
	}

	public String getRoute() {
		return route;
	}

	public void setRoute(String route) {
		this.route = route;
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

	public Map<String, Object> getInputSummary() {
		return inputSummary;
	}

	public void setInputSummary(Map<String, Object> inputSummary) {
		this.inputSummary = inputSummary;
	}

	public Map<String, Object> getOutputSummary() {
		return outputSummary;
	}

	public void setOutputSummary(Map<String, Object> outputSummary) {
		this.outputSummary = outputSummary;
	}

	public String getError() {
		return error;
	}

	public void setError(String error) {
		this.error = error;
	}

}
