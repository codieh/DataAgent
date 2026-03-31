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

	public DocumentChunker(@Value("${search.lite.document.chunk.max-chars:400}") int maxChars) {
		this.maxChars = Math.max(100, maxChars);
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
		List<String> pieces = new ArrayList<>();
		int start = 0;
		while (start < text.length()) {
			int end = Math.min(start + maxChars, text.length());
			if (end < text.length()) {
				int paragraphBreak = text.lastIndexOf("\n\n", end);
				if (paragraphBreak > start + maxChars / 2) {
					end = paragraphBreak;
				}
				else {
					int sentenceBreak = Math.max(text.lastIndexOf('。', end), text.lastIndexOf('\n', end));
					if (sentenceBreak > start + maxChars / 2) {
						end = sentenceBreak + 1;
					}
				}
			}
			String piece = text.substring(start, end).trim();
			if (!piece.isBlank()) {
				pieces.add(piece);
			}
			start = Math.max(end, start + 1);
		}
		return pieces;
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
