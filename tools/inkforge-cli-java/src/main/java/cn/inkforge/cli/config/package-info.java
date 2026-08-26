/**
 * CLI profile、Core origin 与系统安全凭据后端。
 *
 * <p>配置文件不保存 Cookie；生产凭据只能进入 macOS Keychain 或 Windows Credential Manager，
 * 不支持的平台必须明确失败，不能为了可用性降级为明文文件。
 */
package cn.inkforge.cli.config;
