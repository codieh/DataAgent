package com.alibaba.cloud.ai.dataagentbackend.lite.sql;

import org.springframework.util.StringUtils;

import java.util.Locale;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * SQL 安全校验与轻量规范化工具（精简版）。
 *
 * <p>
 * 目标：在本地 Demo 中避免明显危险/不可控的 SQL，同时保持实现简单易懂。
 * </p>
 *
 * <p>
 * 注意：这不是一个完整 SQL 解析器；生产环境应使用 SQL parser + 白名单策略。
 * </p>
 */
public final class SqlGuards {

	private SqlGuards() {
	}

	private static final Pattern AS_ALIAS = Pattern.compile("(?i)\\s+as\\s+([a-zA-Z_][a-zA-Z0-9_]*)");

	/**
	 * 一小部分 MySQL 保留字/特殊标识，遇到时给 alias 加反引号，降低语法错误概率。
	 * <p>
	 * 说明：这里只覆盖常见坑（例如模型喜欢输出 current_user 作为别名）。
	 * </p>
	 */
	private static final Set<String> RESERVED_ALIAS = Set.of("current_user", "user", "system", "order", "group");

	/**
	 * 只允许单条 SELECT 语句（不允许分号、多语句、DML/DDL）。
	 */
	public static void validateSelectOnly(String sql) {
		String normalized = normalize(sql);
		if (!StringUtils.hasText(normalized)) {
			throw new IllegalArgumentException("SQL 为空");
		}
		// 禁止多语句（最简单的判定：包含分号）
		if (normalized.contains(";")) {
			throw new IllegalArgumentException("SQL 不允许包含分号（仅允许单条语句）");
		}

		String lower = normalized.toLowerCase(Locale.ROOT);
		if (!lower.startsWith("select")) {
			throw new IllegalArgumentException("仅允许 SELECT 查询");
		}

		// 额外的关键字黑名单（防止模型输出危险语句）
		if (containsAny(lower, "insert ", "update ", "delete ", "drop ", "truncate ", "alter ", "create ",
				"replace ", "grant ", "revoke ")) {
			throw new IllegalArgumentException("SQL 包含不允许的写入/DDL 关键字");
		}
	}

	/**
	 * 如果没有 LIMIT，则追加 LIMIT。
	 */
	public static String ensureLimit(String sql, int limit) {
		String normalized = escapeReservedAliases(normalize(sql));
		String lower = normalized.toLowerCase(Locale.ROOT);
		if (lower.contains(" limit ")) {
			return normalized;
		}
		// 简化处理：直接追加。对 MySQL 的简单 SELECT 足够。
		return normalized + " LIMIT " + Math.max(1, limit);
	}

	/**
	 * 将部分保留字别名转义为 `alias`，避免出现 "AS current_user" 这类语法错误。
	 */
	public static String escapeReservedAliases(String sql) {
		if (!StringUtils.hasText(sql)) {
			return "";
		}
		Matcher m = AS_ALIAS.matcher(sql);
		StringBuffer sb = new StringBuffer();
		while (m.find()) {
			String alias = m.group(1);
			if (alias != null && RESERVED_ALIAS.contains(alias.toLowerCase(Locale.ROOT))) {
				m.appendReplacement(sb, " AS `" + alias + "`");
			}
			else {
				m.appendReplacement(sb, m.group(0));
			}
		}
		m.appendTail(sb);
		return sb.toString();
	}

	/**
	 * 简化 normalize：去除代码围栏、trim、压缩空白。
	 */
	public static String normalize(String sql) {
		if (sql == null) {
			return "";
		}
		String s = sql.trim();
		s = s.replace("```sql", "").replace("```SQL", "").replace("```", "").trim();
		// 将连续空白压缩为单空格，便于 contains 判断
		s = s.replaceAll("\\s+", " ");
		return s.trim();
	}

	private static boolean containsAny(String text, String... needles) {
		if (!StringUtils.hasText(text) || needles == null) {
			return false;
		}
		for (String n : needles) {
			if (n != null && text.contains(n)) {
				return true;
			}
		}
		return false;
	}

}
