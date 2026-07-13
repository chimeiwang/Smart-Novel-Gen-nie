# OpenAPI 客户端换行符漂移检查规格

## 背景

Windows 根仓库可能依据 Git 配置把已提交的 `schema.d.ts` 检出为 CRLF，而 `openapi-typescript` 的内存生成结果固定使用 LF。两者接口内容一致，但 `api:check` 直接比较原始字符串时会误报客户端漂移。

## 目标

- `npm run api:check` 在 LF 与 CRLF 仅换行符不同的情况下通过。
- 任何非换行符差异仍然明确失败。
- `api:generate` 的输出内容和 OpenAPI 契约保持不变。

## 非目标

- 不修改 Git 全局换行符配置。
- 不放宽空白、字段、路由或类型差异。
- 不修改 PostgreSQL schema 或运行时 API。

## 设计

生成器在 `--check` 分支中分别把当前文件和内存生成结果的 `\r\n`、孤立 `\r` 规范化为 `\n`，再执行严格相等比较。写入分支仍直接写入生成结果，不做其他格式重写。

## 验收

- 架构测试证明比较双方都经过同一换行规范化函数。
- `npm run api:check` 在 Windows 根仓库通过。
- TypeScript 类型检查和生产构建继续通过。
