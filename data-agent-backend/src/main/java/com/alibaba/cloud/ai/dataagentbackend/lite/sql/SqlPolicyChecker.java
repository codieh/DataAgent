package com.alibaba.cloud.ai.dataagentbackend.lite.sql;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Set;

@Component
public class SqlPolicyChecker {

	private final Set<String> sensitiveFieldKeywords;

	public SqlPolicyChecker(
			@Value("${search.lite.sql.guard.sensitive-fields:phone,mobile,email,id_card,idcard,salary,wage,address,bank_card}") String sensitiveFields) {
		this.sensitiveFieldKeywords = Arrays.stream(sensitiveFields.split(","))
			.map(String::trim)
			.filter(StringUtils::hasText)
			.map(value -> value.toLowerCase(Locale.ROOT))
			.collect(LinkedHashSet::new, LinkedHashSet::add, LinkedHashSet::addAll);
	}

	public PolicyDecision inspect(String sql) {
		String normalized = SqlGuards.normalize(sql);
		if (!StringUtils.hasText(normalized)) {
			return PolicyDecision.allow();
		}
		String lower = normalized.toLowerCase(Locale.ROOT);
		if (containsSensitiveField(lower)) {
			return PolicyDecision.block("blocked_sensitive_sql",
					"SQL 命中了敏感字段，当前策略不允许直接查询或导出这类明细。");
		}
		if (containsSelectAll(lower)) {
			return PolicyDecision.block("blocked_wide_export", "SQL 使用了 SELECT *，可能导致大范围明细导出。");
		}
		if (looksLikeWideDetailExport(lower)) {
			return PolicyDecision.block("blocked_wide_export", "SQL 缺少 LIMIT 且看起来像明细导出查询，已被安全策略拦截。");
		}
		return PolicyDecision.allow();
	}

	private boolean containsSensitiveField(String lowerSql) {
		for (String keyword : sensitiveFieldKeywords) {
			if (lowerSql.contains(keyword)) {
				return true;
			}
		}
		return false;
	}

	private static boolean containsSelectAll(String lowerSql) {
		return lowerSql.startsWith("select * ") || lowerSql.contains(" select * ") || lowerSql.contains(", * ");
	}

	private static boolean looksLikeWideDetailExport(String lowerSql) {
		if (lowerSql.contains(" limit ") || isAggregateQuery(lowerSql)) {
			return false;
		}
		return lowerSql.startsWith("select ");
	}

	private static boolean isAggregateQuery(String lowerSql) {
		return lowerSql.contains(" count(") || lowerSql.contains(" sum(") || lowerSql.contains(" avg(")
				|| lowerSql.contains(" min(") || lowerSql.contains(" max(") || lowerSql.contains(" group by ");
	}

	public record PolicyDecision(boolean blocked, String resultMode, String reason) {
		public static PolicyDecision allow() {
			return new PolicyDecision(false, null, null);
		}

		public static PolicyDecision block(String resultMode, String reason) {
			return new PolicyDecision(true, resultMode, reason);
		}
	}

}
