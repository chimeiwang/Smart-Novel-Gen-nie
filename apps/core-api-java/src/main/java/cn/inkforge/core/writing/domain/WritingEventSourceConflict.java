package cn.inkforge.core.writing.domain;

/** 同一来源事件标识被复用于不同事件事实。 */
public final class WritingEventSourceConflict extends RuntimeException {}
