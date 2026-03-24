package com.alibaba.cloud.ai.dataagentbackend.lite.step.impl;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaColumn;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaForeignKey;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaTable;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessageType;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteMessages;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStepResult;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * 从已抽取的 schema 中，选择本次请求最相关的少量数据表（TopK）。
 *
 * <p>
 * 目的：
 * <ul>
 *   <li>避免把全量 schema 都喂给模型（噪声大、token 多）。</li>
 *   <li>为后续 SQL 生成提供更聚焦的 {@code recalledSchemaText}。</li>
 * </ul>
 * </p>
 *
 * <p>
 * 当前策略：基于 query + evidenceText 的粗糙关键词匹配打分。
 * 后续可替换为向量检索（更接近 management 的做法）。
 * </p>
 */
@Component
@Order(32)
public class SchemaRecallStep implements SearchLiteStep {

	private static final Logger log = LoggerFactory.getLogger(SchemaRecallStep.class);

	/**
	 * 英文/数字 token 切分。
	 */
	private static final Pattern SPLIT = Pattern.compile("[^\\p{IsAlphabetic}\\p{IsDigit}]+");

	/**
	 * 中文片段提取（连续 CJK 字符）。
	 */
	private static final Pattern CJK = Pattern.compile("[\\p{IsHan}]{2,}");

	private final int topK;

	public SchemaRecallStep(@Value("${search.lite.schema.recall.top-k:3}") int topK) {
		this.topK = Math.max(1, topK);
	}

	@Override
	public SearchLiteStage stage() {
		return SearchLiteStage.SCHEMA_RECALL;
	}

	@Override
	public SearchLiteStepResult run(SearchLiteContext context, SearchLiteState state) {
		Flux<SearchLiteMessage> start = Flux
			.just(SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT, "正在选择相关数据表（schema recall）...", null))
			.delayElements(Duration.ofMillis(40));

		List<SchemaTable> tables = state.getSchemaTableDetails();
		if (tables == null || tables.isEmpty()) {
			Flux<SearchLiteMessage> msg = Flux.just(SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT,
					"未发现可用 schema，请先初始化/抽取 schema。", null));
			return new SearchLiteStepResult(start.concatWith(msg), Mono.just(state));
		}

		String query = safe(state.getQuery());
		String evidence = safe(state.getEvidenceText());
		Set<String> tokens = tokenizeMixed(query + "\n" + evidence);

		List<ScoredTable> selected = tables.stream()
			.map(t -> new ScoredTable(t, score(t, tokens)))
			.filter(st -> st.score > 0)
			.sorted(Comparator.<ScoredTable>comparingDouble(st -> st.score).reversed())
			.limit(topK)
			.toList();

		// 如果全部为 0（比如 query 很短/无中文 token 命中），退化为选前 topK 张表
		if (selected.isEmpty()) {
			selected = tables.stream().limit(topK).map(t -> new ScoredTable(t, 0)).toList();
		}

		List<SchemaTable> recalled = selected.stream().map(st -> st.table).toList();
		List<String> recalledNames = recalled.stream().map(SchemaTable::name).toList();
		String recalledSchemaText = formatForPrompt(recalled);

		log.info("schema recall：threadId={}, recalledTables={}", context.threadId(), recalledNames);
		state.setRecalledTables(recalledNames);
		state.setRecalledSchemaText(recalledSchemaText);

		Flux<SearchLiteMessage> tableMsg = Flux.just(SearchLiteMessages.message(context, stage(),
				SearchLiteMessageType.TEXT, "已选择表: " + String.join(", ", recalledNames), null));

		Flux<SearchLiteMessage> payload = Flux.just(SearchLiteMessages.message(context, stage(),
				SearchLiteMessageType.JSON, null, Map.of("recalledTables", recalledNames, "recalledSchemaTextLen",
						recalledSchemaText.length(), "tokenCount", tokens.size())));

		return new SearchLiteStepResult(start.concatWith(tableMsg).concatWith(payload), Mono.just(state));
	}

	private static Set<String> tokenizeMixed(String text) {
		if (!StringUtils.hasText(text)) {
			return Set.of();
		}

		String lower = text.toLowerCase(Locale.ROOT);
		Set<String> tokens = SPLIT.splitAsStream(lower)
			.filter(StringUtils::hasText)
			.filter(s -> s.length() >= 2)
			.collect(Collectors.toSet());

		Matcher m = CJK.matcher(text);
		while (m.find()) {
			String seg = m.group();
			if (!StringUtils.hasText(seg)) {
				continue;
			}
			String trimmed = seg.trim();
			if (trimmed.length() < 2) {
				continue;
			}
			// 加入整段
			tokens.add(trimmed);
			// 加入 2-gram，提升短词命中率（如“订单”“商品”）
			for (int i = 0; i < trimmed.length() - 1; i++) {
				tokens.add(trimmed.substring(i, i + 2));
			}
		}

		return tokens;
	}

	private static double score(SchemaTable table, Set<String> tokens) {
		if (table == null || tokens == null || tokens.isEmpty()) {
			return 0;
		}

		StringBuilder sb = new StringBuilder();
		sb.append(safe(table.name())).append(" ").append(safe(table.comment())).append(" ");
		if (table.columns() != null) {
			for (SchemaColumn c : table.columns()) {
				sb.append(safe(c.name())).append(" ").append(safe(c.comment())).append(" ");
			}
		}
		if (table.foreignKeys() != null) {
			for (SchemaForeignKey fk : table.foreignKeys()) {
				sb.append(safe(fk.columnName())).append(" ").append(safe(fk.refTableName())).append(" ")
					.append(safe(fk.refColumnName())).append(" ");
			}
		}

		String haystack = sb.toString().toLowerCase(Locale.ROOT);
		double score = 0;
		for (String token : tokens) {
			if (!StringUtils.hasText(token)) {
				continue;
			}
			if (haystack.contains(token.toLowerCase(Locale.ROOT))) {
				score += 1.0;
			}
		}
		return score;
	}

	private static String formatForPrompt(List<SchemaTable> tables) {
		if (tables == null || tables.isEmpty()) {
			return "(无 schema)";
		}
		StringBuilder sb = new StringBuilder();
		sb.append("数据库 Schema（本次相关表）\n");
		for (SchemaTable table : tables) {
			sb.append("\n");
			sb.append("TABLE ").append(safe(table.name()));
			if (StringUtils.hasText(table.comment())) {
				sb.append(" -- ").append(table.comment().trim());
			}
			sb.append("\n");

			if (table.columns() != null) {
				for (SchemaColumn col : table.columns()) {
					sb.append("  - ").append(safe(col.name())).append(" ").append(safe(col.columnType(), col.dataType()));
					if (col.primaryKey()) {
						sb.append(" PK");
					}
					if (col.notNull()) {
						sb.append(" NOT_NULL");
					}
					if (StringUtils.hasText(col.comment())) {
						sb.append(" -- ").append(col.comment().trim());
					}
					sb.append("\n");
				}
			}

			if (table.foreignKeys() != null && !table.foreignKeys().isEmpty()) {
				sb.append("  FK:\n");
				for (SchemaForeignKey fk : table.foreignKeys()) {
					sb.append("    - ").append(safe(fk.columnName())).append(" -> ").append(safe(fk.refTableName()))
						.append(".").append(safe(fk.refColumnName())).append("\n");
				}
			}
		}
		return sb.toString().trim();
	}

	private static String safe(String s) {
		return s == null ? "" : s.trim();
	}

	private static String safe(String... parts) {
		for (String p : parts) {
			if (StringUtils.hasText(p)) {
				return p.trim();
			}
		}
		return "";
	}

	private record ScoredTable(SchemaTable table, double score) {
	}

}

