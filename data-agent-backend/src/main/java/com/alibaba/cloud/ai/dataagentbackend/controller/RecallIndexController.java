package com.alibaba.cloud.ai.dataagentbackend.controller;

import com.alibaba.cloud.ai.dataagentbackend.lite.recall.RecallIndexInitializer;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.RecallService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import java.util.Map;

/**
 * 检索索引初始化 / 重建接口。
 */
@RestController
@RequestMapping("/api/index")
public class RecallIndexController {

	private final RecallIndexInitializer recallIndexInitializer;

	private final RecallService recallService;

	public RecallIndexController(RecallIndexInitializer recallIndexInitializer, RecallService recallService) {
		this.recallIndexInitializer = recallIndexInitializer;
		this.recallService = recallService;
	}

	@GetMapping("/status")
	public Mono<Object> status() {
		return Mono.fromCallable(recallService::indexStatus).subscribeOn(Schedulers.boundedElastic()).cast(Object.class);
	}

	@PostMapping("/init/evidence")
	public Mono<Map<String, Object>> initEvidence() {
		return Mono.fromCallable(recallIndexInitializer::rebuildEvidenceIndex).subscribeOn(Schedulers.boundedElastic());
	}

	@PostMapping("/init/schema")
	public Mono<Map<String, Object>> initSchema() {
		return Mono.fromCallable(recallIndexInitializer::rebuildSchemaIndex).subscribeOn(Schedulers.boundedElastic());
	}

	@PostMapping("/init/documents")
	public Mono<Map<String, Object>> initDocuments() {
		return Mono.fromCallable(recallIndexInitializer::rebuildDocumentIndex).subscribeOn(Schedulers.boundedElastic());
	}

	@PostMapping("/init/all")
	public Mono<Map<String, Object>> initAll() {
		return Mono.fromCallable(recallIndexInitializer::rebuildAll).subscribeOn(Schedulers.boundedElastic());
	}

}
