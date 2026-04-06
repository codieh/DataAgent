package com.alibaba.cloud.ai.dataagentbackend.lite.conversation;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 参考 management 的做法，按 threadId 维护最近几轮对话窗口，并生成可注入 prompt 的多轮上下文。
 */
@Component
public class MultiTurnContextManager {

	private static final String EMPTY_CONTEXT = "(无)";

	private final Map<String, Deque<ConversationTurn>> history = new ConcurrentHashMap<>();

	private final Map<String, PendingConversationTurn> pendingTurns = new ConcurrentHashMap<>();

	private final int maxTurnHistory;

	private final int maxFieldLength;

	public MultiTurnContextManager(@Value("${search.lite.context.max-turn-history:5}") int maxTurnHistory,
			@Value("${search.lite.context.max-field-length:240}") int maxFieldLength) {
		this.maxTurnHistory = Math.max(1, maxTurnHistory);
		this.maxFieldLength = Math.max(40, maxFieldLength);
	}

	public PreparedConversationContext prepareTurn(String threadId, String userQuery) {
		String multiTurnContext = buildContext(threadId);
		String contextualizedQuery = buildContextualizedQuery(threadId, userQuery);
		beginTurn(threadId, userQuery, contextualizedQuery);
		return new PreparedConversationContext(multiTurnContext, contextualizedQuery);
	}

	public void beginTurn(String threadId, String userQuery, String contextualizedQuery) {
		if (!StringUtils.hasText(threadId) || !StringUtils.hasText(userQuery)) {
			return;
		}
		pendingTurns.put(threadId, new PendingConversationTurn(userQuery.trim(), safe(contextualizedQuery)));
	}

	public void finishTurn(SearchLiteState state) {
		if (state == null || !StringUtils.hasText(state.getThreadId())) {
			return;
		}
		String threadId = state.getThreadId();
		PendingConversationTurn pending = pendingTurns.remove(threadId);
		if (pending == null || !shouldPersistTurn(state)) {
			return;
		}

		ConversationTurn turn = new ConversationTurn(abbreviate(pending.userQuery()),
				abbreviate(firstNonBlank(state.getContextualizedQuery(), pending.contextualizedQuery())),
				abbreviate(state.getCanonicalQuery()), abbreviate(state.getSql()), abbreviate(selectResultSummary(state)),
				abbreviate(state.getIntentClassification()));

		Deque<ConversationTurn> deque = history.computeIfAbsent(threadId, key -> new ArrayDeque<>());
		synchronized (deque) {
			while (deque.size() >= maxTurnHistory) {
				deque.pollFirst();
			}
			deque.addLast(turn);
		}
	}

	public void discardPending(String threadId) {
		if (!StringUtils.hasText(threadId)) {
			return;
		}
		pendingTurns.remove(threadId);
	}

	public String buildContext(String threadId) {
		if (!StringUtils.hasText(threadId)) {
			return EMPTY_CONTEXT;
		}
		Deque<ConversationTurn> deque = history.get(threadId);
		if (deque == null || deque.isEmpty()) {
			return EMPTY_CONTEXT;
		}
		StringBuilder builder = new StringBuilder();
		int index = 1;
		for (ConversationTurn turn : deque) {
			if (builder.length() > 0) {
				builder.append("\n\n");
			}
			builder.append("[最近第").append(index++).append("轮]");
			appendLine(builder, "用户问题", turn.userQuery());
			appendLine(builder, "上下文补全", turn.contextualizedQuery());
			appendLine(builder, "规范化问题", turn.canonicalQuery());
			appendLine(builder, "SQL", turn.sql());
			appendLine(builder, "结果摘要", turn.resultSummary());
		}
		return builder.length() == 0 ? EMPTY_CONTEXT : builder.toString();
	}

	private String buildContextualizedQuery(String threadId, String userQuery) {
		String normalizedQuery = safe(userQuery);
		if (!StringUtils.hasText(threadId) || !StringUtils.hasText(normalizedQuery) || !isContextDependent(normalizedQuery)) {
			return normalizedQuery;
		}
		ConversationTurn latest = latestTurn(threadId);
		if (latest == null || !StringUtils.hasText(latest.anchorQuery())) {
			return normalizedQuery;
		}
		String anchor = abbreviate(latest.anchorQuery());
		if (startsWithAny(normalizedQuery, "改成", "换成", "改为", "换为")) {
			return "基于上一轮查询“" + anchor + "”，将查询条件调整为：" + normalizedQuery;
		}
		return "基于上一轮查询“" + anchor + "”，当前追问：" + normalizedQuery;
	}

	private ConversationTurn latestTurn(String threadId) {
		Deque<ConversationTurn> deque = history.get(threadId);
		if (deque == null || deque.isEmpty()) {
			return null;
		}
		synchronized (deque) {
			return deque.peekLast();
		}
	}

	private boolean shouldPersistTurn(SearchLiteState state) {
		if ("DATA_ANALYSIS".equalsIgnoreCase(state.getIntentClassification())) {
			return true;
		}
		return StringUtils.hasText(state.getCanonicalQuery()) || StringUtils.hasText(state.getSql())
				|| StringUtils.hasText(state.getResultSummary()) || StringUtils.hasText(state.getError());
	}

	private String selectResultSummary(SearchLiteState state) {
		if (StringUtils.hasText(state.getResultSummary())) {
			return state.getResultSummary();
		}
		if (StringUtils.hasText(state.getError())) {
			return "执行失败：" + state.getError();
		}
		return "";
	}

	private boolean isContextDependent(String query) {
		return containsAny(query, "这些", "它们", "他们", "其中", "里面", "前面", "刚才", "刚刚", "上面", "上述", "上一轮", "上一个")
				|| startsWithAny(query, "再", "继续", "改成", "换成", "改为", "换为", "那", "那就");
	}

	private static boolean containsAny(String text, String... needles) {
		for (String needle : needles) {
			if (text.contains(needle)) {
				return true;
			}
		}
		return false;
	}

	private static boolean startsWithAny(String text, String... prefixes) {
		for (String prefix : prefixes) {
			if (text.startsWith(prefix)) {
				return true;
			}
		}
		return false;
	}

	private void appendLine(StringBuilder builder, String label, String value) {
		if (!StringUtils.hasText(value)) {
			return;
		}
		builder.append("\n").append(label).append(": ").append(value.trim());
	}

	private String abbreviate(String text) {
		String normalized = safe(text);
		if (!StringUtils.hasText(normalized) || normalized.length() <= maxFieldLength) {
			return normalized;
		}
		return normalized.substring(0, maxFieldLength - 3) + "...";
	}

	private static String safe(String text) {
		return text == null ? "" : text.trim();
	}

	private static String firstNonBlank(String... values) {
		for (String value : values) {
			if (StringUtils.hasText(value)) {
				return value.trim();
			}
		}
		return "";
	}

}
