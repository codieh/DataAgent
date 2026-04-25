package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessageType;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLitePlanStep;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteMessages;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphMessageEmitter;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateMapper;
import com.alibaba.cloud.ai.dataagentbackend.llm.anthropic.AnthropicClient;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.NodeAction;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

@Component
public class SearchLitePlannerGraphNode implements NodeAction {

	private static final Logger log = LoggerFactory.getLogger(SearchLitePlannerGraphNode.class);

	private final AnthropicClient anthropicClient;

	private final ObjectMapper objectMapper;

	private final SearchLiteGraphMessageEmitter messageEmitter;

	private final int maxSteps;

	public SearchLitePlannerGraphNode(AnthropicClient anthropicClient, ObjectMapper objectMapper,
			SearchLiteGraphMessageEmitter messageEmitter,
			@Value("${search.lite.graph.planner.max-steps:5}") int maxSteps) {
		this.anthropicClient = Objects.requireNonNull(anthropicClient, "anthropicClient");
		this.objectMapper = Objects.requireNonNull(objectMapper, "objectMapper");
		this.messageEmitter = Objects.requireNonNull(messageEmitter, "messageEmitter");
		this.maxSteps = Math.max(1, maxSteps);
	}

	@Override
	public Map<String, Object> apply(OverAllState state) {
		SearchLiteState liteState = SearchLiteGraphStateMapper.toSearchLiteState(state);
		SearchLiteContext context = new SearchLiteContext(resolveThreadId(liteState));
		messageEmitter.emitOne(context.threadId(), SearchLiteMessages.message(context, SearchLiteStage.PLANNER,
				SearchLiteMessageType.TEXT, "正在规划分析步骤...", null));

		String system = """
				You are a senior data analysis planner.
				Split the request into a concise, executable SQL-first plan.
				Return ONLY valid JSON without markdown or extra commentary.
				""".trim();
		String user = buildPlannerPrompt(liteState);
		String rawOutput;
		try {
			rawOutput = anthropicClient.createMessage(system, user).blockOptional().orElse("");
		}
		catch (Exception ex) {
			rawOutput = "";
			log.warn("planner llm generation failed: threadId={}, error={}", context.threadId(), ex.getMessage());
		}

		PlannerOutput plannerOutput = parsePlannerOutput(rawOutput, liteState);
		liteState.setPlanSteps(plannerOutput.steps());
		liteState.setCurrentPlanStepIndex(0);
		liteState.setPlannerEnabled(plannerOutput.steps().size() > 1);
		liteState.setPlanFinished(false);
		liteState.setPlannerRawOutput(rawOutput);
		liteState.setPlanValidationStatus(true);
		liteState.setPlanValidationError(null);

		messageEmitter.emitOne(context.threadId(), SearchLiteMessages.done(context, SearchLiteStage.PLANNER,
				SearchLiteMessageType.JSON, null,
				Map.of("steps", plannerOutput.steps(), "plannerEnabled", liteState.isPlannerEnabled(),
						"rawPlanLen", rawOutput == null ? 0 : rawOutput.length())));
		log.info("graph planner node invoked: steps={}, plannerEnabled={}, repairCount={}", plannerOutput.steps().size(),
				liteState.isPlannerEnabled(), liteState.getPlanRepairCount());
		return SearchLiteGraphStateMapper.fromSearchLiteState(liteState);
	}

	private String buildPlannerPrompt(SearchLiteState state) {
		StringBuilder prompt = new StringBuilder("""
				Create a SQL-only execution plan for the current data analysis request.

				Output JSON schema:
				{
				  "steps": [
				    {
				      "step": 1,
				      "instruction": "...",
				      "tool": "SQL"
				    }
				  ]
				}

				Rules:
				- Only use tool value "SQL".
				- Create 1 to %d steps.
				- Each step instruction must be self-contained and executable by a SQL generator.
				- If the query is simple, return exactly one step.
				- If the query has multiple dependent asks, decompose into ordered SQL steps.
				- Do not invent unavailable business constraints.
				- Prefer minimal step count.
				- If prior plan validation failed, fix the issues explicitly.

				User request:
				%s

				Canonical query:
				%s

				Multi-turn context:
				%s

				Schema context:
				%s

				Evidence context:
				%s

				Document context:
				%s
				""".formatted(maxSteps, safe(state.getQuery()), safe(state.getCanonicalQuery()),
					safeOrDefault(state.getMultiTurnContext(), "(无)"), safeOrDefault(state.getRecalledSchemaText(), "(无)"),
					safeOrDefault(state.getEvidenceText(), "(无)"), safeOrDefault(state.getDocumentText(), "(无)")));

		if (StringUtils.hasText(state.getPlanValidationError())) {
			prompt.append("\nPrevious plan validation error:\n").append(state.getPlanValidationError()).append('\n');
			prompt.append("\nPrevious raw plan:\n").append(safeOrDefault(state.getPlannerRawOutput(), "(无)")).append('\n');
		}
		return prompt.toString().trim();
	}

	private PlannerOutput parsePlannerOutput(String raw, SearchLiteState state) {
		String query = resolvePlanQuery(state);
		List<SearchLitePlanStep> fallback = List.of(new SearchLitePlanStep(1, query));
		if (!StringUtils.hasText(raw)) {
			return new PlannerOutput(fallback);
		}
		try {
			String json = extractJsonObject(raw.trim());
			PlannerOutputPayload payload = objectMapper.readValue(json, PlannerOutputPayload.class);
			List<SearchLitePlanStep> normalized = normalizeSteps(payload == null ? null : payload.steps(), query);
			return new PlannerOutput(normalized.isEmpty() ? fallback : normalized);
		}
		catch (Exception ex) {
			log.warn("planner output parse failed, fallback to single-step plan: {}", ex.getMessage());
			return new PlannerOutput(fallback);
		}
	}

	private List<SearchLitePlanStep> normalizeSteps(List<PlannerOutputStep> rawSteps, String fallbackQuery) {
		if (rawSteps == null || rawSteps.isEmpty()) {
			return List.of();
		}
		List<SearchLitePlanStep> normalized = new ArrayList<>();
		int nextStep = 1;
		for (PlannerOutputStep rawStep : rawSteps) {
			if (rawStep == null || !StringUtils.hasText(rawStep.instruction())) {
				continue;
			}
			if (!"SQL".equalsIgnoreCase(safeOrDefault(rawStep.tool(), "SQL"))) {
				continue;
			}
			SearchLitePlanStep step = new SearchLitePlanStep(nextStep++, rawStep.instruction().trim());
			step.setTool("SQL");
			step.setStatus("PENDING");
			normalized.add(step);
			if (normalized.size() >= maxSteps) {
				break;
			}
		}
		if (normalized.isEmpty() && StringUtils.hasText(fallbackQuery)) {
			normalized.add(new SearchLitePlanStep(1, fallbackQuery));
		}
		return normalized;
	}

	private String extractJsonObject(String text) {
		int start = text.indexOf('{');
		int end = text.lastIndexOf('}');
		if (start >= 0 && end > start) {
			return text.substring(start, end + 1);
		}
		return text;
	}

	private String resolvePlanQuery(SearchLiteState state) {
		if (StringUtils.hasText(state.getCanonicalQuery())) {
			return state.getCanonicalQuery();
		}
		if (StringUtils.hasText(state.getContextualizedQuery())) {
			return state.getContextualizedQuery();
		}
		return safe(state.getQuery());
	}

	private String resolveThreadId(SearchLiteState state) {
		if (StringUtils.hasText(state.getThreadId())) {
			return state.getThreadId();
		}
		String generated = "graph-planner-" + UUID.randomUUID();
		state.setThreadId(generated);
		return generated;
	}

	private String safe(String value) {
		return value == null ? "" : value.trim();
	}

	private String safeOrDefault(String value, String fallback) {
		return StringUtils.hasText(value) ? value.trim() : fallback;
	}

	private record PlannerOutput(List<SearchLitePlanStep> steps) {
	}

	private record PlannerOutputPayload(List<PlannerOutputStep> steps) {
	}

	private record PlannerOutputStep(Integer step, String instruction, String tool) {
	}

}
