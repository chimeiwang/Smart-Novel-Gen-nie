/**
 * Java CLI 的进程入口、命令注册与稳定错误信封。
 *
 * <p>除 {@code auth.login} 外不接受 argv 业务参数；每次调用从 stdin 读取一个完整 UTF-8 JSON 对象，
 * stdout 只输出约定的 JSON/JSONL，诊断进入 stderr，避免脚本调用方把日志误当作业务结果。
 */
package cn.inkforge.cli.runtime;
