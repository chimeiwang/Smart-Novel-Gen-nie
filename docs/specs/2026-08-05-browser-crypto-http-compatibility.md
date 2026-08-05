# 浏览器密码学 API 的 HTTP 兼容规格

## 背景

生产环境暂时通过公网 IP 的 HTTP 地址访问。登录成功进入 `/dashboard` 后，`CreateNovelModal` 在初始化状态时直接调用 `crypto.randomUUID()`；中短篇选区修改还会调用 `crypto.subtle.digest()`。这两个 API 在当前浏览器的非安全上下文中不可用，会分别导致工作台渲染和选区修改流程异常。

## 目标

- 公网 HTTP 环境能够正常渲染工作台并执行需要 `clientRequestId` 的操作。
- 公网 HTTP 环境能够计算与 Core 完全一致的选区文本 SHA-256。
- 安全上下文继续优先使用浏览器原生 `crypto.randomUUID()` 和 `crypto.subtle.digest()`。
- 所有浏览器端 `clientRequestId` 统一通过同一个工具函数生成。

## 非目标

- 不修改认证、Cookie、Core API、数据库结构或部署入口。
- 不引入第三方 UUID 或哈希依赖。
- 不使用 `Math.random()` 生成幂等请求 ID，也不使用非 SHA-256 算法替代选区哈希。

## 设计

### 请求 ID

在 `apps/web/src/lib/api/client-request-id.ts` 提供 `createClientRequestId()`：

1. `crypto.randomUUID` 存在时直接调用并返回。
2. 否则通过 `crypto.getRandomValues()` 填充 16 字节随机数。
3. 设置 UUID v4 的版本位和 RFC 4122 变体位，再格式化为标准 UUID 字符串。
4. 工作台、中短篇工作流和写作会话中的直接调用全部替换为该函数。

### 选区 SHA-256

在 `apps/web/src/features/short-medium/sha256.ts` 提供 `sha256Text()`：

1. 使用 `TextEncoder` 对原始文本进行 UTF-8 编码，不做换行或 Unicode 归一化。
2. `crypto.subtle.digest` 存在时继续使用原生 SHA-256。
3. 缺失时使用纯 TypeScript SHA-256 回退，输出 64 位小写十六进制字符串。
4. `selection-range.ts` 只负责选区范围与身份组装，哈希实现由独立模块负责。

## 验收标准

1. 单元测试证明原生 UUID 能力存在时优先使用原生实现。
2. 单元测试证明缺少 `randomUUID` 时能够生成格式、版本位和变体位正确的 UUID v4。
3. 标准 SHA-256 测试向量通过，中文、换行和 Emoji 在原生与回退路径结果一致。
4. `apps/web/src` 除兼容工具内部外不再直接调用 `crypto.randomUUID()` 或 `crypto.subtle.digest()`。
5. Web 测试、类型检查、Lint 和生产构建通过。
