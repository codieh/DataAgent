package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 检索阶段共用的轻量分词工具。
 */
public final class RecallTokenizers {

	private static final Pattern SPLIT = Pattern.compile("[^\\p{IsAlphabetic}\\p{IsDigit}]+");

	private static final Pattern CJK = Pattern.compile("[\\p{IsHan}]{2,}");

	private RecallTokenizers() {
	}

	public static Set<String> tokenizeMixed(String text) {
		if (text == null || text.isBlank()) {
			return Set.of();
		}

		Set<String> tokens = new LinkedHashSet<>();
		SPLIT.splitAsStream(text.toLowerCase(Locale.ROOT))
			.filter(token -> token != null && !token.isBlank())
			.filter(token -> token.length() >= 2)
			.forEach(tokens::add);

		Matcher matcher = CJK.matcher(text);
		while (matcher.find()) {
			String segment = matcher.group();
			if (segment == null || segment.isBlank()) {
				continue;
			}
			String trimmed = segment.trim();
			if (trimmed.length() < 2) {
				continue;
			}
			tokens.add(trimmed);
			for (int i = 0; i < trimmed.length() - 1; i++) {
				tokens.add(trimmed.substring(i, i + 2));
			}
		}

		return tokens;
	}

}
