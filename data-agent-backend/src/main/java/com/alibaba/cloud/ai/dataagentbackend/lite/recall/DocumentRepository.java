package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Stream;

/**
 * 本地文档仓库。
 *
 * <p>
 * Step 5.1 先支持读取本地 md/txt/json 文件，并将每个文件作为一个最小文档单元。
 * 更细粒度的切块会在后续步骤继续增强。
 * </p>
 */
@Component
public class DocumentRepository {

	private final Path documentsDir;

	private final DocumentChunker documentChunker;

	public DocumentRepository(@Value("${search.lite.document.dir:./data/documents}") String documentsDir,
			DocumentChunker documentChunker) {
		this.documentsDir = Path.of(documentsDir).toAbsolutePath().normalize();
		this.documentChunker = documentChunker;
	}

	public List<DocumentIndexBuilder.SourceDocument> listAll() {
		if (!Files.exists(documentsDir)) {
			return List.of();
		}
		try (Stream<Path> stream = Files.walk(documentsDir)) {
			return stream.filter(Files::isRegularFile)
				.filter(this::isSupported)
				.sorted(Comparator.comparing(path -> path.toString().toLowerCase(Locale.ROOT)))
				.flatMap(path -> toSourceDocuments(path).stream())
				.toList();
		}
		catch (IOException e) {
			throw new IllegalStateException("读取本地文档目录失败: " + documentsDir, e);
		}
	}

	public Path documentsDir() {
		return documentsDir;
	}

	public DocumentSourceStatus status() {
		if (!Files.exists(documentsDir)) {
			return new DocumentSourceStatus(documentsDir.toString(), false, 0, 0);
		}
		List<DocumentIndexBuilder.SourceDocument> chunks = listAll();
		Set<String> files = chunks.stream().map(doc -> doc.relativePath().toString()).collect(java.util.stream.Collectors.toSet());
		return new DocumentSourceStatus(documentsDir.toString(), true, files.size(), chunks.size());
	}

	private List<DocumentIndexBuilder.SourceDocument> toSourceDocuments(Path path) {
		try {
			String content = Files.readString(path, StandardCharsets.UTF_8);
			Path relativePath = documentsDir.relativize(path);
			String fileName = path.getFileName().toString();
			String fileType = extensionOf(fileName);
			String baseName = stripExtension(fileName);
			return documentChunker.chunk(baseName, relativePath, fileType, content);
		}
		catch (IOException e) {
			throw new IllegalStateException("读取文档失败: " + path, e);
		}
	}

	private boolean isSupported(Path path) {
		String extension = extensionOf(path.getFileName().toString());
		return extension.equals("md") || extension.equals("txt") || extension.equals("json");
	}

	private static String extensionOf(String fileName) {
		int dot = fileName.lastIndexOf('.');
		return dot >= 0 ? fileName.substring(dot + 1).toLowerCase(Locale.ROOT) : "";
	}

	private static String stripExtension(String fileName) {
		int dot = fileName.lastIndexOf('.');
		return dot >= 0 ? fileName.substring(0, dot) : fileName;
	}

}
