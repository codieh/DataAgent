package com.alibaba.cloud.ai.dataagentbackend.lite.eval;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

@Component
public class EvalCaseLoader {

	private final ObjectMapper objectMapper;

	private final Path casesDir;

	public EvalCaseLoader(ObjectMapper objectMapper,
			@Value("${search.lite.eval.cases-dir:D:/GitHub/DataAgent/data-agent-backend/data/eval/cases}") String casesDir) {
		this.objectMapper = objectMapper;
		this.casesDir = Path.of(casesDir);
	}

	public List<LoadedEvalDataset> loadAll() throws IOException {
		if (!Files.exists(casesDir)) {
			return List.of();
		}
		try (Stream<Path> stream = Files.list(casesDir)) {
			return stream.filter(path -> Files.isRegularFile(path) && path.getFileName().toString().endsWith(".json"))
				.sorted(Comparator.comparing(path -> path.getFileName().toString()))
				.map(this::readDataset)
				.toList();
		}
	}

	private LoadedEvalDataset readDataset(Path path) {
		try {
			return new LoadedEvalDataset(path, objectMapper.readValue(path.toFile(), EvalCaseDataset.class));
		}
		catch (IOException ex) {
			throw new IllegalStateException("failed to read eval dataset: " + path, ex);
		}
	}

	public record LoadedEvalDataset(Path path, EvalCaseDataset dataset) {
	}

}
