package com.alibaba.cloud.ai.dataagentbackend.lite.eval;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;

@Component
public class EvalReportWriter {

	private static final DateTimeFormatter FILE_TS_FORMAT = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss")
		.withZone(ZoneId.systemDefault());

	private final ObjectMapper objectMapper;

	private final EvalMarkdownReportRenderer markdownReportRenderer;

	private final Path reportsDir;

	public EvalReportWriter(ObjectMapper objectMapper, EvalMarkdownReportRenderer markdownReportRenderer,
			@Value("${search.lite.eval.reports-dir:D:/GitHub/DataAgent/data-agent-backend/data/eval-reports}") String reportsDir) {
		this.objectMapper = objectMapper;
		this.markdownReportRenderer = markdownReportRenderer;
		this.reportsDir = Path.of(reportsDir);
	}

	public void write(EvalRunReport report) throws IOException {
		Files.createDirectories(reportsDir);
		String timestamp = FILE_TS_FORMAT.format(report.generatedAt());
		Path latestJson = reportsDir.resolve("latest-report.json");
		Path latestMd = reportsDir.resolve("latest-report.md");
		Path archiveJson = reportsDir.resolve("report-" + timestamp + ".json");
		Path archiveMd = reportsDir.resolve("report-" + timestamp + ".md");

		objectMapper.writerWithDefaultPrettyPrinter().writeValue(latestJson.toFile(), report);
		objectMapper.writerWithDefaultPrettyPrinter().writeValue(archiveJson.toFile(), report);

		String markdown = markdownReportRenderer.render(report);
		Files.writeString(latestMd, markdown, StandardCharsets.UTF_8);
		Files.writeString(archiveMd, markdown, StandardCharsets.UTF_8);
	}

}
