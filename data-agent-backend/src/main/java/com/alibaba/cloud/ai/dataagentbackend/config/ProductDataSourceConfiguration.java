package com.alibaba.cloud.ai.dataagentbackend.config;

import com.zaxxer.hikari.HikariDataSource;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.JdbcTemplate;

import javax.sql.DataSource;

@Configuration
public class ProductDataSourceConfiguration {

	@Bean
	@Primary
	@ConfigurationProperties("spring.datasource")
	public DataSourceProperties productDataSourceProperties() {
		return new DataSourceProperties();
	}

	@Bean
	@Primary
	@ConfigurationProperties("spring.datasource.hikari")
	public DataSource dataSource(DataSourceProperties productDataSourceProperties) {
		return productDataSourceProperties.initializeDataSourceBuilder().type(HikariDataSource.class).build();
	}

	@Bean
	@Primary
	public JdbcTemplate jdbcTemplate(DataSource dataSource) {
		return new JdbcTemplate(dataSource);
	}

}
