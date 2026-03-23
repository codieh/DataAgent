package com.alibaba.cloud.ai.dataagentbackend.lite.evidence;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.EvidenceItem;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.InputStream;
import java.util.Collections;
import java.util.List;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Component;

@Component
public class EvidenceRepository {

	private static final String DEFAULT_RESOURCE = "evidence/evidence.json";

	private final ObjectMapper objectMapper;

	private volatile List<EvidenceItem> cached = List.of();

	public EvidenceRepository(ObjectMapper objectMapper) {
		this.objectMapper = objectMapper;
		this.cached = loadFromClasspath(DEFAULT_RESOURCE);
	}

	public List<EvidenceItem> listAll() {
		return cached;
	}

	private List<EvidenceItem> loadFromClasspath(String path) {
		try (InputStream in = new ClassPathResource(path).getInputStream()) {
			List<EvidenceItem> items = objectMapper.readValue(in, new TypeReference<>() {
			});
			return items == null ? List.of() : items;
		}
		catch (Exception ignored) {
			return Collections.emptyList();
		}
	}

}

