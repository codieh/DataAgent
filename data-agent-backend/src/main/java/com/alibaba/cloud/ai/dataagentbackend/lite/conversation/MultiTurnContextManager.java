package com.alibaba.cloud.ai.dataagentbackend.lite.conversation;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;

/**
 * 参考 management 的做法，按 threadId 维护最近几轮对话窗口，并生成可注入 prompt 的多轮上下文。
 */
@Component
public class MultiTurnContextManager {

	private static final String EMPTY_CONTEXT = "(无)";

	private final Map<String, Deque<ConversationTurn>> history = new ConcurrentHashMap<>();

	private final Map<String, PendingConversationTurn> pendingTurns = new ConcurrentHashMap<>();

	private final Map<String, String> rollingSummaries = new ConcurrentHashMap<>();

	private final Map<String, Long> lastAccessAt = new ConcurrentHashMap<>();

	private final int maxTurnHistory;

	private final int maxFieldLength;

	private final int recentDetailTurns;

	private final long ttlMillis;

	private final int maxActiveThreads;

	public MultiTurnContextManager(@Value("${search.lite.context.max-turn-history:5}") int maxTurnHistory,
			@Value("${search.lite.context.max-field-length:240}") int maxFieldLength,
			@Value("${search.lite.context.recent-detail-turns:3}") int recentDetailTurns,
			@Value("${search.lite.context.ttl-minutes:180}") long ttlMinutes,
			@Value("${search.lite.context.max-active-threads:1000}") int maxActiveThreads) {
		this.maxTurnHistory = Math.max(1, maxTurnHistory);
		this.maxFieldLength = Math.max(40, maxFieldLength);
		this.recentDetailTurns = Math.max(1, recentDetailTurns);
		this.ttlMillis = Math.max(TimeUnit.MINUTES.toMillis(10), TimeUnit.MINUTES.toMillis(ttlMinutes));
		this.maxActiveThreads = Math.max(1, maxActiveThreads);
	}

	public PreparedConversationContext prepareTurn(String threadId, String userQuery) {
		cleanupIfNeeded();
		touch(threadId);
		String multiTurnContext = buildContext(threadId);
		String contextualizedQuery = buildContextualizedQuery(threadId, userQuery);
		beginTurn(threadId, userQuery, contextualizedQuery);
		return new PreparedConversationContext(multiTurnContext, contextualizedQuery);
	}

	public void beginTurn(String threadId, String userQuery, String contextualizedQuery) {
		if (!StringUtils.hasText(threadId) || !StringUtils.hasText(userQuery)) {
			return;
		}
		touch(threadId);
		pendingTurns.put(threadId, new PendingConversationTurn(userQuery.trim(), safe(contextualizedQuery)));
	}

	public void finishTurn(SearchLiteState state) {
		if (state == null || !StringUtils.hasText(state.getThreadId())) {
			return;
		}
		String threadId = state.getThreadId();
		cleanupIfNeeded();
		touch(threadId);
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
			deque.addLast(turn);
			summarizeIfNeeded(threadId, deque);
		}
	}

	public void discardPending(String threadId) {
		if (!StringUtils.hasText(threadId)) {
			return;
		}
		pendingTurns.remove(threadId);
		touch(threadId);
	}

	public String buildContext(String threadId) {
		if (!StringUtils.hasText(threadId)) {
			return EMPTY_CONTEXT;
		}
		cleanupIfNeeded();
		touch(threadId);
		Deque<ConversationTurn> deque = history.get(threadId);
		String rollingSummary = safe(rollingSummaries.get(threadId));
		if ((deque == null || deque.isEmpty()) && !StringUtils.hasText(rollingSummary)) {
			return EMPTY_CONTEXT;
		}
		StringBuilder builder = new StringBuilder();
		if (StringUtils.hasText(rollingSummary)) {
			builder.append("[会话滚动摘要]");
			appendLine(builder, "摘要", rollingSummary);
		}
		if (deque != null && !deque.isEmpty()) {
			List<ConversationTurn> turns = recentTurns(deque);
			int index = 1;
			for (ConversationTurn turn : turns) {
				if (builder.length() > 0) {
					builder.append("\n\n");
				}
				builder.append("[最近第").append(index++).append("轮详情]");
				appendLine(builder, "用户问题", turn.userQuery());
				appendLine(builder, "上下文补全", turn.contextualizedQuery());
				appendLine(builder, "规范化问题", turn.canonicalQuery());
				appendLine(builder, "SQL", turn.sql());
				appendLine(builder, "结果摘要", turn.resultSummary());
			}
		}
		return builder.length() == 0 ? EMPTY_CONTEXT : builder.toString();
	}

	private List<ConversationTurn> recentTurns(Deque<ConversationTurn> deque) {
		synchronized (deque) {
			int size = deque.size();
			int skip = Math.max(0, size - recentDetailTurns);
			List<ConversationTurn> turns = new java.util.ArrayList<>(Math.min(size, recentDetailTurns));
			int index = 0;
			for (ConversationTurn turn : deque) {
				if (index++ < skip) {
					continue;
				}
				turns.add(turn);
			}
			return turns;
		}
	}

	private void summarizeIfNeeded(String threadId, Deque<ConversationTurn> deque) {
		if (maxTurnHistory <= recentDetailTurns) {
			while (deque.size() > maxTurnHistory) {
				deque.pollFirst();
			}
			return;
		}
		if (deque.size() < maxTurnHistory || deque.size() <= recentDetailTurns) {
			return;
		}
		int summarizeCount = deque.size() - recentDetailTurns;
		String summary = rollingSummaries.get(threadId);
		for (int i = 0; i < summarizeCount; i++) {
			ConversationTurn archived = deque.pollFirst();
			if (archived != null) {
				summary = mergeSummary(summary, archived);
			}
		}
		if (StringUtils.hasText(summary)) {
			rollingSummaries.put(threadId, summary);
		}
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
		touch(threadId);
		synchronized (deque) {
			return deque.peekLast();
		}
	}

	private void cleanupIfNeeded() {
		evictExpiredThreads();
		evictOverflowThreads();
	}

	private void evictExpiredThreads() {
		long now = System.currentTimeMillis();
		for (Map.Entry<String, Long> entry : lastAccessAt.entrySet()) {
			Long lastAccess = entry.getValue();
			if (lastAccess == null || now - lastAccess < ttlMillis) {
				continue;
			}
			removeThread(entry.getKey(), lastAccess);
		}
	}

	private void evictOverflowThreads() {
		int overflow = lastAccessAt.size() - maxActiveThreads;
		if (overflow <= 0) {
			return;
		}
		lastAccessAt.entrySet()
			.stream()
			.sorted(Map.Entry.comparingByValue(Comparator.nullsFirst(Long::compareTo)))
			.limit(overflow)
			.map(Map.Entry::getKey)
			.toList()
			.forEach(this::removeThread);
	}

	private void removeThread(String threadId) {
		removeThread(threadId, lastAccessAt.get(threadId));
	}

	private void removeThread(String threadId, Long expectedLastAccess) {
		if (!StringUtils.hasText(threadId)) {
			return;
		}
		if (expectedLastAccess != null && !lastAccessAt.remove(threadId, expectedLastAccess)) {
			return;
		}
		if (expectedLastAccess == null) {
			lastAccessAt.remove(threadId);
		}
		history.remove(threadId);
		pendingTurns.remove(threadId);
		rollingSummaries.remove(threadId);
	}

	private void touch(String threadId) {
		if (!StringUtils.hasText(threadId)) {
			return;
		}
		lastAccessAt.put(threadId, System.currentTimeMillis());
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

	private String mergeSummary(String existingSummary, ConversationTurn turn) {
		StringBuilder builder = new StringBuilder();
		String topic = firstNonBlank(turn.canonicalQuery(), turn.contextualizedQuery(), turn.userQuery());
		String result = firstNonBlank(turn.resultSummary(), turn.sql());
		String intent = safe(turn.intentClassification());
		if (StringUtils.hasText(existingSummary)) {
			builder.append(existingSummary.trim());
		}
		if (StringUtils.hasText(topic)) {
			appendMergedLine(builder, "当前主题", topic);
		}
		if (StringUtils.hasText(result)) {
			appendMergedLine(builder, "最近结果", result);
		}
		if (StringUtils.hasText(intent)) {
			appendMergedLine(builder, "意图", intent);
		}
		String merged = builder.toString().trim();
		return abbreviate(merged);
	}

	private void appendMergedLine(StringBuilder builder, String label, String value) {
		if (!StringUtils.hasText(value)) {
			return;
		}
		if (builder.length() > 0) {
			builder.append("\n");
		}
		builder.append(label).append(": ").append(abbreviate(value));
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
