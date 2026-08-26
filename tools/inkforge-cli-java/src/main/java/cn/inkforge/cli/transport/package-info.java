/**
 * CLI 的公共 HTTP、SSE、multipart 与原子文件传输层。
 *
 * <p>远端只允许 HTTPS，本地 HTTP 只允许回环地址；会话 Cookie 不进入日志、输出或进程参数。
 * 文本和二进制结果均完整传输，文件写入使用同目录临时文件同步后原子替换。
 */
package cn.inkforge.cli.transport;
