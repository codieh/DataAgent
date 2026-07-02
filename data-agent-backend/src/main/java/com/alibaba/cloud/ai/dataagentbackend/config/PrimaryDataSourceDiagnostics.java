package com.alibaba.cloud.ai.dataagentbackend.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.DatabaseMetaData;

@Component
public class PrimaryDataSourceDiagnostics implements ApplicationRunner {

	private static final Logger log = LoggerFactory.getLogger(PrimaryDataSourceDiagnostics.class);

	private final DataSource dataSource;

	private final JdbcTemplate jdbcTemplate;

	public PrimaryDataSourceDiagnostics(DataSource dataSource, JdbcTemplate jdbcTemplate) {
		this.dataSource = dataSource;
		this.jdbcTemplate = jdbcTemplate;
	}

	@Override
	public void run(ApplicationArguments args) {
		try (Connection connection = dataSource.getConnection()) {
			DatabaseMetaData metaData = connection.getMetaData();
			String jdbcUrl = safe(metaData.getURL());
			String driverName = safe(metaData.getDriverName());
			String productName = safe(metaData.getDatabaseProductName());
			String productVersion = safe(metaData.getDatabaseProductVersion());
			String catalog = safe(connection.getCatalog());
			String schema = safe(connection.getSchema());
			String currentDatabase = currentDatabase();
			log.info(
					"primary datasource detected: jdbcUrl={}, driver={}, product={}, version={}, catalog={}, schema={}, currentDatabase={}",
					jdbcUrl, driverName, productName, productVersion, catalog, schema, currentDatabase);
		}
		catch (Exception ex) {
			log.warn("primary datasource diagnostics failed: {}", ex.getMessage(), ex);
		}
	}

	private String currentDatabase() {
		try {
			return safe(jdbcTemplate.queryForObject("SELECT DATABASE()", String.class));
		}
		catch (Exception ex) {
			return "n/a(" + ex.getClass().getSimpleName() + ": " + safe(ex.getMessage()) + ")";
		}
	}

	private static String safe(String value) {
		return value == null || value.isBlank() ? "(blank)" : value;
	}

}
