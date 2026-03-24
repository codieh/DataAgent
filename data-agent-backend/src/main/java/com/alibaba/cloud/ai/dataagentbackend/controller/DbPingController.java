package com.alibaba.cloud.ai.dataagentbackend.controller;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import java.util.Map;

/**
 * 数据库连通性检查。
 *
 * <p>
 * 说明：
 * <ul>
 *   <li>这是 Step7.1 的最小交付：先把 product_db 接入并验证能连通。</li>
 *   <li>注意：JDBC 是阻塞式调用，因此必须切到 {@code boundedElastic} 线程池，避免阻塞 WebFlux 事件循环线程。</li>
 * </ul>
 * </p>
 */
@RestController
@RequestMapping("/api/db")
public class DbPingController {

	private final JdbcTemplate jdbcTemplate;

	public DbPingController(JdbcTemplate jdbcTemplate) {
		this.jdbcTemplate = jdbcTemplate;
	}

	@GetMapping("/ping")
	public Mono<Map<String, Object>> ping() {
		return Mono.fromCallable(() -> {
			Integer result = jdbcTemplate.queryForObject("SELECT 1", Integer.class);
			return Map.<String, Object>of("ok", true, "result", result);
		}).subscribeOn(Schedulers.boundedElastic())
			.onErrorResume(e -> Mono.just(Map.<String, Object>of("ok", false, "error", e.getMessage())));
	}

}
