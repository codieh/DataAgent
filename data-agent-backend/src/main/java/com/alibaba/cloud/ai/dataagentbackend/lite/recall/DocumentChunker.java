package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * 文档切块器。
 *
 * <p>
 * V1 采用“标题 + 段落优先、长度兜底”的轻量策略：
 * </p>
 * <ul>
 * <li>Markdown：先按标题切 section，再按段落聚合，超长再切分</li>
 * <li>txt/json：先按空行分段，再按长度切分</li>
 * </ul>
 */
@Component
public class DocumentChunker {

	private final int maxChars;

	private final int overlapChars;

	public DocumentChunker(@Value("${search.lite.document.chunk.max-chars:400}") int maxChars,
			@Value("${search.lite.document.chunk.overlap-chars:80}") int overlapChars) {
		this.maxChars = Math.max(100, maxChars);
		this.overlapChars = Math.max(0, Math.min(overlapChars, this.maxChars / 2));
	}

	public List<DocumentIndexBuilder.SourceDocument> chunk(String docName, Path relativePath, String fileType, String content) {
		if (content == null || content.isBlank()) {
			return List.of();
		}
		String normalizedType = fileType == null ? "" : fileType.trim().toLowerCase(Locale.ROOT);
		List<Section> sections = switch (normalizedType) {
			case "md" -> splitMarkdown(docName, content);
			case "txt", "json" -> splitPlain(docName, content);
			default -> splitPlain(docName, content);
		};

		List<DocumentIndexBuilder.SourceDocument> chunks = new ArrayList<>();
		int chunkIndex = 0;
		for (Section section : sections) {
			for (String piece : splitByLength(section.content())) {
				if (piece.isBlank()) {
					continue;
				}
				chunks.add(new DocumentIndexBuilder.SourceDocument(
						"document:" + relativePath.toString().replace('\\', '/') + "#" + chunkIndex,
						docName,
						section.title(),
						chunkIndex,
						relativePath,
						normalizedType,
						piece));
				chunkIndex++;
			}
		}
		return List.copyOf(chunks);
	}

	private List<Section> splitMarkdown(String docName, String content) {
		List<Section> sections = new ArrayList<>();
		String currentTitle = docName;
		StringBuilder current = new StringBuilder();
		for (String rawLine : content.replace("\r\n", "\n").split("\n")) {
			String line = rawLine == null ? "" : rawLine.stripTrailing();
			if (line.stripLeading().startsWith("#")) {
				addSection(sections, currentTitle, current);
				currentTitle = normalizeHeading(line);
				current = new StringBuilder();
				continue;
			}
			appendLine(current, line);
		}
		addSection(sections, currentTitle, current);
		return sections.isEmpty() ? List.of(new Section(docName, content.trim())) : sections;
	}

	private List<Section> splitPlain(String docName, String content) {
		List<Section> sections = new ArrayList<>();
		StringBuilder current = new StringBuilder();
		for (String rawLine : content.replace("\r\n", "\n").split("\n")) {
			String line = rawLine == null ? "" : rawLine.stripTrailing();
			if (line.isBlank()) {
				addSection(sections, docName, current);
				current = new StringBuilder();
				continue;
			}
			appendLine(current, line);
		}
		addSection(sections, docName, current);
		return sections.isEmpty() ? List.of(new Section(docName, content.trim())) : sections;
	}

	private List<String> splitByLength(String content) {
		String text = content == null ? "" : content.trim();
		if (text.isBlank()) {
			return List.of();
		}
		if (text.length() <= maxChars) {
			return List.of(text);
		}
		List<String> sentences = splitSentences(text);
		if (sentences.size() <= 1) {
			return splitBySlidingWindow(text);
		}
		return splitSentencesWithOverlap(sentences);
	}

	private List<String> splitSentencesWithOverlap(List<String> sentences) {
		List<String> pieces = new ArrayList<>();
		int index = 0;
		while (index < sentences.size()) {
			StringBuilder current = new StringBuilder();
			int endExclusive = index;
			while (endExclusive < sentences.size()) {
				String sentence = sentences.get(endExclusive);
				if (current.length() > 0 && current.length() + 1 + sentence.length() > maxChars) {
					break;
				}
				if (current.length() > 0) {
					current.append('\n');
				}
				current.append(sentence);
				endExclusive++;
			}
			if (endExclusive == index) {
				String sentence = sentences.get(index);
				pieces.addAll(splitBySlidingWindow(sentence));
				index++;
				continue;
			}
			pieces.add(current.toString().trim());
			if (endExclusive >= sentences.size()) {
				break;
			}
			index = rewindForOverlap(sentences, index, endExclusive);
		}
		return pieces;
	}

	private int rewindForOverlap(List<String> sentences, int startInclusive, int endExclusive) {
		if (overlapChars <= 0) {
			return endExclusive;
		}
		int overlapLength = 0;
		for (int i = endExclusive - 1; i >= startInclusive; i--) {
			String sentence = sentences.get(i);
			int candidate = overlapLength + sentence.length();
			if (overlapLength > 0) {
				candidate += 1;
			}
			if (candidate > overlapChars) {
				return i == endExclusive - 1 ? endExclusive - 1 : i + 1;
			}
			overlapLength = candidate;
		}
		return startInclusive + 1;
	}

	private List<String> splitBySlidingWindow(String text) {
		List<String> pieces = new ArrayList<>();
		int step = Math.max(1, maxChars - overlapChars);
		int start = 0;
		while (start < text.length()) {
			int end = Math.min(start + maxChars, text.length());
			String piece = text.substring(start, end).trim();
			if (!piece.isBlank()) {
				pieces.add(piece);
			}
			if (end >= text.length()) {
				break;
			}
			start = Math.min(start + step, text.length() - 1);
		}
		return pieces;
	}

	private List<String> splitSentences(String text) {
		List<String> sentences = new ArrayList<>();
		StringBuilder current = new StringBuilder();
		for (int i = 0; i < text.length(); i++) {
			char ch = text.charAt(i);
			current.append(ch);
			if (isSentenceBoundary(ch)) {
				addSentence(sentences, current);
				current = new StringBuilder();
			}
		}
		addSentence(sentences, current);
		return sentences;
	}

	private void addSentence(List<String> sentences, StringBuilder current) {
		String normalized = current == null ? "" : current.toString().trim();
		if (!normalized.isBlank()) {
			sentences.add(normalized);
		}
	}

	private boolean isSentenceBoundary(char ch) {
		return ch == '。' || ch == '！' || ch == '？' || ch == '.' || ch == '!' || ch == '?' || ch == '\n';
	}

	private static void addSection(List<Section> sections, String title, StringBuilder current) {
		String text = current == null ? "" : current.toString().trim();
		if (!text.isBlank()) {
			sections.add(new Section(title == null || title.isBlank() ? "Untitled" : title.trim(), text));
		}
	}

	private static void appendLine(StringBuilder current, String line) {
		if (current.length() > 0) {
			current.append('\n');
		}
		current.append(line == null ? "" : line.trim());
	}

	private static String normalizeHeading(String line) {
		String text = line == null ? "" : line.stripLeading();
		int index = 0;
		while (index < text.length() && text.charAt(index) == '#') {
			index++;
		}
		return text.substring(index).trim();
	}

	private record Section(String title, String content) {
	}

}
