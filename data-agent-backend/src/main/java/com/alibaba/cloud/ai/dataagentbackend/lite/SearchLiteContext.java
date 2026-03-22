package com.alibaba.cloud.ai.dataagentbackend.lite;

import java.time.Instant;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Per-request runtime context for the lite pipeline (e.g. message sequencing).
 */
public final class SearchLiteContext {

	private final String threadId;

	private final AtomicLong seq;

	private final Instant startTime;

	public SearchLiteContext(String threadId) {
		this(threadId, new AtomicLong(0), Instant.now());
	}

	public SearchLiteContext(String threadId, AtomicLong seq, Instant startTime) {
		this.threadId = Objects.requireNonNull(threadId, "threadId");
		this.seq = Objects.requireNonNull(seq, "seq");
		this.startTime = Objects.requireNonNull(startTime, "startTime");
	}

	public String threadId() {
		return threadId;
	}

	public long nextSeq() {
		return seq.incrementAndGet();
	}

	public Instant startTime() {
		return startTime;
	}

}

