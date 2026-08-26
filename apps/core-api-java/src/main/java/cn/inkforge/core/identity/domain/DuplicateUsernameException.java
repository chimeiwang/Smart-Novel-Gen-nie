package cn.inkforge.core.identity.domain;

/** 只表示 PostgreSQL 精确用户名唯一约束冲突。 */
public final class DuplicateUsernameException extends RuntimeException {}
