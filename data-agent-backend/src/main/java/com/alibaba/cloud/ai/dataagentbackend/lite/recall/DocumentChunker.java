package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

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

	private static final Pattern PARAGRAPH_PATTERN = Pattern.compile("\\n\\s*\\n+");

	private static final Pattern SENTENCE_PATTERN = Pattern.compile("[^。！？.!?\\n]+[。！？.!?\\n]*");

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
		return splitParagraphsWithOverlap(text);
	}

	private List<String> splitParagraphsWithOverlap(String text) {
		List<String> pieces = new ArrayList<>();
		String[] paragraphs = PARAGRAPH_PATTERN.split(text.replace("\r\n", "\n"));
		StringBuilder current = new StringBuilder();
		for (String paragraph : paragraphs) {
			String trimmedParagraph = paragraph == null ? "" : paragraph.trim();
			if (trimmedParagraph.isBlank()) {
				continue;
			}
			if (trimmedParagraph.length() > maxChars) {
				if (current.length() > 0) {
					pieces.add(current.toString().trim());
					current = extractOverlap(current.toString());
				}
				for (String subChunk : splitLargeParagraph(trimmedParagraph)) {
					if (subChunk.isBlank()) {
						continue;
					}
					int potentialLen = current.length() + (current.length() > 0 ? 2 : 0) + subChunk.length();
					if (potentialLen > maxChars && current.length() > 0) {
						current = new StringBuilder();
					}
					if (current.length() > 0) {
						current.append("\n\n");
					}
					current.append(subChunk);
					pieces.add(current.toString().trim());
					current = extractOverlap(current.toString());
				}
				continue;
			}
			int separatorLength = current.length() > 0 ? 2 : 0;
			int potentialLength = current.length() + separatorLength + trimmedParagraph.length();
			if (potentialLength > maxChars && current.length() > 0) {
				pieces.add(current.toString().trim());
				current = extractOverlap(current.toString());
			}
			if (current.length() > 0) {
				current.append("\n\n");
			}
			current.append(trimmedParagraph);
		}
		if (current.length() > 0) {
			pieces.add(current.toString().trim());
		}
		return pieces;
	}

	private StringBuilder extractOverlap(String chunk) {
		if (overlapChars <= 0 || chunk == null || chunk.isEmpty()) {
			return new StringBuilder();
		}
		int length = chunk.length();
		if (length <= overlapChars) {
			return new StringBuilder(chunk);
		}
		String rawOverlap = chunk.substring(length - overlapChars);
		int firstParagraphBreak = rawOverlap.indexOf("\n\n");
		if (firstParagraphBreak != -1 && firstParagraphBreak + 2 < rawOverlap.length()) {
			return new StringBuilder(rawOverlap.substring(firstParagraphBreak + 2));
		}
		return new StringBuilder(rawOverlap.trim());
	}

	private List<String> splitLargeParagraph(String paragraph) {
		List<String> subChunks = new ArrayList<>();
		Matcher matcher = SENTENCE_PATTERN.matcher(paragraph);
		StringBuilder current = new StringBuilder();
		int lastMatchEnd = 0;
		while (matcher.find()) {
			String sentence = matcher.group();
			lastMatchEnd = matcher.end();
			if (sentence.length() > maxChars) {
				if (current.length() > 0) {
					subChunks.add(current.toString().trim());
					current = new StringBuilder();
				}
				subChunks.addAll(splitBySlidingWindow(sentence));
				continue;
			}
			if (current.length() + sentence.length() > maxChars && current.length() > 0) {
				subChunks.add(current.toString().trim());
				current = new StringBuilder();
			}
			current.append(sentence);
		}
		if (lastMatchEnd < paragraph.length()) {
			String remaining = paragraph.substring(lastMatchEnd).trim();
			if (!remaining.isBlank()) {
				if (remaining.length() > maxChars) {
					if (current.length() > 0) {
						subChunks.add(current.toString().trim());
						current = new StringBuilder();
					}
					subChunks.addAll(splitBySlidingWindow(remaining));
				}
				else {
					if (current.length() + remaining.length() > maxChars && current.length() > 0) {
						subChunks.add(current.toString().trim());
						current = new StringBuilder();
					}
					current.append(remaining);
				}
			}
		}
		if (current.length() > 0) {
			subChunks.add(current.toString().trim());
		}
		return subChunks;
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
