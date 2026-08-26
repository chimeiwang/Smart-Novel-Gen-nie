/**
 * 125 个稳定 CLI 命令到公共 Core HTTP/SSE 操作的映射。
 *
 * <p>命令只负责严格解析 stdin、构造公共请求和格式化 stdout；归属、CAS、审核与功能门禁仍由 Core 决定。
 * watcher 只停止本地观察，不能把中断传播为远端任务取消。
 */
package cn.inkforge.cli.commands;
