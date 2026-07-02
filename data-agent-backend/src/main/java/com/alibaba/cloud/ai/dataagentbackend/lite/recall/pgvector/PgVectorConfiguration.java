package com.alibaba.cloud.ai.dataagentbackend.lite.recall.pgvector;

import com.zaxxer.hikari.HikariDataSource;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

import javax.sql.DataSource;
import java.net.URI;
import java.util.Locale;

@Configuration
@EnableConfigurationProperties(PgVectorProperties.class)
public class PgVectorConfiguration {

	private static final Logger log = LoggerFactory.getLogger(PgVectorConfiguration.class);

	private static final String JDBC_PREFIX = "jdbc:postgresql://";

	private final int maximumPoolSize;

	private final int minimumIdle;

	private final long connectionTimeoutMs;

	private final long validationTimeoutMs;

	public PgVectorConfiguration(
			@Value("${search.lite.recall.pgvector.pool.maximum-size:20}") int maximumPoolSize,
			@Value("${search.lite.recall.pgvector.pool.minimum-idle:2}") int minimumIdle,
			@Value("${search.lite.recall.pgvector.pool.connection-timeout-ms:5000}") long connectionTimeoutMs,
			@Value("${search.lite.recall.pgvector.pool.validation-timeout-ms:3000}") long validationTimeoutMs) {
		this.maximumPoolSize = Math.max(1, maximumPoolSize);
		this.minimumIdle = Math.max(0, Math.min(this.maximumPoolSize, minimumIdle));
		this.connectionTimeoutMs = Math.max(1000L, connectionTimeoutMs);
		this.validationTimeoutMs = Math.max(1000L, validationTimeoutMs);
	}

	@Bean(name = "pgVectorDataSource")
	public DataSource pgVectorDataSource(PgVectorProperties properties) {
		HikariDataSource dataSource = new HikariDataSource();
		dataSource.setPoolName("pgvector-hikari");
		dataSource.setMaximumPoolSize(maximumPoolSize);
		dataSource.setMinimumIdle(minimumIdle);
		dataSource.setConnectionTimeout(connectionTimeoutMs);
		dataSource.setValidationTimeout(validationTimeoutMs);
		dataSource.setInitializationFailTimeout(-1);
		configurePostgresDataSource(dataSource, properties);
		return dataSource;
	}

	@Bean(name = "pgVectorJdbcTemplate")
	public JdbcTemplate pgVectorJdbcTemplate(@Qualifier("pgVectorDataSource") DataSource dataSource) {
		return new JdbcTemplate(dataSource);
	}

	private void configurePostgresDataSource(HikariDataSource hikari, PgVectorProperties properties) {
		String jdbcUrl = properties.url().trim();
		ParsedJdbcUrl parsed = parseJdbcUrl(jdbcUrl);
		if (parsed == null) {
			hikari.setDriverClassName("org.postgresql.Driver");
			hikari.setJdbcUrl(jdbcUrl);
			hikari.setUsername(properties.username());
			hikari.setPassword(properties.password());
			log.warn("pgvector jdbc url fallback: could not parse '{}', using raw jdbcUrl", jdbcUrl);
			return;
		}
		String normalizedJdbcUrl = "jdbc:postgresql://%s:%d/%s".formatted(normalizeHost(parsed.host()), parsed.port(),
				parsed.database());
		hikari.setDriverClassName("org.postgresql.Driver");
		hikari.setJdbcUrl(normalizedJdbcUrl);
		hikari.setUsername(properties.username());
		hikari.setPassword(properties.password());
		log.info("pgvector datasource configured: host={}, port={}, database={}, maxPoolSize={}, minIdle={}",
				normalizeHost(parsed.host()), parsed.port(), parsed.database(), maximumPoolSize, minimumIdle);
	}

	private ParsedJdbcUrl parseJdbcUrl(String jdbcUrl) {
		if (jdbcUrl == null || jdbcUrl.isBlank() || !jdbcUrl.startsWith(JDBC_PREFIX)) {
			return null;
		}
		try {
			URI uri = URI.create("postgresql://" + jdbcUrl.substring(JDBC_PREFIX.length()));
			String host = uri.getHost();
			int port = uri.getPort() > 0 ? uri.getPort() : 5432;
			String path = uri.getPath();
			String database = path == null ? "" : path.replaceFirst("^/", "").trim();
			if (host == null || host.isBlank() || database.isBlank()) {
				return null;
			}
			return new ParsedJdbcUrl(host.trim(), port, database);
		}
		catch (Exception ex) {
			log.warn("pgvector jdbc url parse failed: {}", ex.getMessage());
			return null;
		}
	}

	private String normalizeHost(String host) {
		if (host == null || host.isBlank()) {
			return "localhost";
		}
		String normalized = host.trim();
		if ("127.0.0.1".equals(normalized) || "0.0.0.0".equals(normalized)) {
			return "localhost";
		}
		return normalized.toLowerCase(Locale.ROOT);
	}

	private record ParsedJdbcUrl(String host, int port, String database) {
	}

}
