# 浏览器密码学 API 的 HTTP 兼容实施计划

**目标：** 修复公网 HTTP 环境中 UUID 与 SHA-256 浏览器 API 不可用导致的工作台和选区修改异常。

**架构：** 请求 ID 工具优先使用原生 UUID，缺失时用 Web Crypto 随机字节生成 UUID v4；选区哈希优先使用原生 SubtleCrypto，缺失时用无依赖的 TypeScript SHA-256。调用方只依赖兼容工具，不感知协议差异。

**技术栈：** TypeScript、Web Crypto、Node.js Test Runner、Next.js 16

---

### 任务 1：兼容请求 ID

**文件：**

- 新增：`apps/web/src/lib/api/client-request-id.ts`
- 新增：`apps/web/src/lib/api/__tests__/client-request-id.test.ts`
- 修改：`apps/web/src/features/projects/create-novel-modal.tsx`
- 修改：`apps/web/src/features/short-medium/short-medium-workspace.tsx`
- 修改：`apps/web/src/features/writing/writing-conversation.tsx`

- [x] 用失败测试定义原生优先和 HTTP 回退行为。
- [x] 实现 UUID v4 回退并通过目标测试。
- [x] 替换全部直接调用并确认没有遗漏。

### 任务 2：兼容选区 SHA-256

**文件：**

- 新增：`apps/web/src/features/short-medium/sha256.ts`
- 新增：`apps/web/src/features/short-medium/__tests__/sha256.test.ts`
- 修改：`apps/web/src/features/short-medium/selection-range.ts`

- [x] 用标准向量和非 ASCII 文本写回退路径失败测试。
- [x] 运行目标测试，确认因兼容模块尚不存在而失败。
- [x] 实现原生优先和纯 TypeScript SHA-256 回退。
- [x] 让选区身份组装使用统一哈希工具并通过目标测试。

### 任务 3：完整验证与发布

- [x] 搜索确认没有遗漏直接调用。
- [x] 运行 `npm run test:web`、`npm run typecheck` 和 `npm run lint`。
- [x] 运行 `npm run build` 并检查生成文件噪声。
- [x] 审查完整差异，只暂存本次 HTTP 兼容修复。
- [ ] 使用简体中文提交信息提交并推送当前 `main`。
- [ ] 核对本地 `HEAD` 与 `origin/main` 一致。
