package com.alibaba.cloud.ai.dataagentbackend.lite.trace;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class SearchLiteTraceRecorder {

	private static final Logger log = LoggerFactory.getLogger(SearchLiteTraceRecorder.class);

	private static final DateTimeFormatter FILE_TIME = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss-SSS")
		.withZone(ZoneId.systemDefault());

	private final ObjectMapper objectMapper;

	private final boolean enabled;

	private final Path baseDir;

	private final ConcurrentHashMap<String, SearchLiteTrace> activeTraces = new ConcurrentHashMap<>();

	public SearchLiteTraceRecorder(ObjectMapper objectMapper,
			@Value("${search.lite.trace.enabled:true}") boolean enabled,
			@Value("${search.lite.trace.dir:D:/GitHub/DataAgent/data-agent-backend/data/traces}") String dir) {
		this.objectMapper = objectMapper;
		this.enabled = enabled;
		this.baseDir = Path.of(dir == null || dir.isBlank() ? "D:/GitHub/DataAgent/data-agent-backend/data/traces" : dir);
	}

	public void startRun(String threadId, String agentId, String query, String mode, boolean resumed) {
		if (!enabled || !StringUtils.hasText(threadId)) {
			return;
		}
		SearchLiteTrace trace = new SearchLiteTrace();
		trace.setTraceId(UUID.randomUUID().toString());
		trace.setThreadId(threadId);
		trace.setAgentId(agentId);
		trace.setQuery(query);
		trace.setMode(mode);
		trace.setResumed(resumed);
		trace.setStartedAt(Instant.now());
		activeTraces.put(threadId, trace);
	}

	public void recordStep(String threadId, SearchLiteStage stage, String route, long durationMs,
			Map<String, Object> inputSummary, Map<String, Object> outputSummary, String error) {
		if (!enabled || !StringUtils.hasText(threadId) || stage == null) {
			return;
		}
		SearchLiteTrace trace = activeTraces.get(threadId);
		if (trace == null) {
			return;
		}
		SearchLiteTraceStep step = new SearchLiteTraceStep();
		step.setStage(stage.name());
		step.setRoute(route == null ? "" : route);
		Instant ended = Instant.now();
		step.setEndedAt(ended);
		step.setStartedAt(ended.minusMillis(Math.max(durationMs, 0)));
		step.setDurationMs(Math.max(durationMs, 0));
		step.setInputSummary(inputSummary);
		step.setOutputSummary(outputSummary);
		step.setError(error);
		synchronized (trace) {
			trace.getSteps().add(step);
		}
	}

	public void recordStage(String threadId, SearchLiteStage stage, String route, long durationMs, SearchLiteState before,
			SearchLiteState after, String error) {
		recordStep(threadId, stage, route, durationMs, SearchLiteTraceSummarizer.summarizeInput(stage, before),
				SearchLiteTraceSummarizer.summarizeOutput(stage, after), error);
	}

	public void finishRun(String threadId, SearchLiteState finalState, String finishSignal) {
		if (!enabled || !StringUtils.hasText(threadId)) {
			return;
		}
		SearchLiteTrace trace = activeTraces.remove(threadId);
		if (trace == null) {
			return;
		}
		Instant endedAt = Instant.now();
		trace.setEndedAt(endedAt);
		if (trace.getStartedAt() != null) {
			trace.setDurationMs(Math.max(0, endedAt.toEpochMilli() - trace.getStartedAt().toEpochMilli()));
		}
		trace.setFinishSignal(finishSignal);
		if (finalState != null) {
			trace.setFinalIntentClassification(finalState.getIntentClassification());
			trace.setFinalResultMode(finalState.getResultMode());
			trace.setFinalPlanFinishedReason(finalState.getPlanFinishedReason());
			trace.setFinalError(finalState.getError());
		}
		writeTrace(trace);
		log.info(
				"trace complete: threadId={}, traceId={}, steps={}, mode={}, resultMode={}, finishSignal={}, durationMs={}",
				trace.getThreadId(), trace.getTraceId(), trace.getSteps().size(), trace.getMode(), trace.getFinalResultMode(),
				trace.getFinishSignal(), trace.getDurationMs());
	}

	private void writeTrace(SearchLiteTrace trace) {
		try {
			Files.createDirectories(baseDir);
			Path output = baseDir.resolve("%s-%s.json".formatted(FILE_TIME.format(trace.getStartedAt()),
					sanitize(trace.getThreadId())));
			objectMapper.writerWithDefaultPrettyPrinter().writeValue(output.toFile(), trace);
		}
		catch (IOException ex) {
			log.warn("trace write failed: threadId={}, error={}", trace.getThreadId(), ex.getMessage());
		}
	}

	private String sanitize(String raw) {
		return raw == null ? "unknown-thread" : raw.replaceAll("[^a-zA-Z0-9\\-_.]", "_");
	}

}
