import Link from "next/link";

import { getSession } from "@/shared/lib/auth";

export default async function HomePage() {
  const session = await getSession();

  return (
    <main className="marketing-page">
      <nav className="marketing-nav" aria-label="官网导航">
        <Link href="/" className="marketing-brand" aria-label="墨铸 InkForge 首页">
          <span className="marketing-brand-mark">墨</span>
          <span>
            <strong>墨铸</strong>
            <small>InkForge</small>
          </span>
        </Link>
        <div className="marketing-nav-actions">
          {session ? (
            <>
              <Link href="/styles" className="marketing-nav-link">
                文风库
              </Link>
              <Link href="/dashboard" className="button">
                进入工作台
              </Link>
            </>
          ) : (
            <>
              <Link href="/login" className="button secondary">
                登录
              </Link>
              <Link href="/login?mode=register" className="button">
                注册开始写作
              </Link>
            </>
          )}
        </div>
      </nav>

      <section className="marketing-hero">
        <div className="marketing-hero-copy">
          <div className="home-kicker">Chinese novel workspace</div>
          <h1>从故事想法到可审核正文草案的中文小说工作台</h1>
          <p>
            墨铸把项目、章节、设定、结构化大纲、文风画像和智能写作流程放在同一个工作台里。
            AI 产物先进入待审核草案，作者确认后才写入正式内容。
          </p>
          <div className="marketing-cta-row">
            {session ? (
              <Link href="/dashboard" className="button marketing-primary-cta">
                打开我的作品
              </Link>
            ) : (
              <Link href="/login?mode=register" className="button marketing-primary-cta">
                注册并领取 1000 积分
              </Link>
            )}
            <Link href="#workflow" className="button ghost">
              查看工作流
            </Link>
          </div>
          <div className="marketing-proof-row" aria-label="核心事实">
            <span>作品规划</span>
            <span>智能协作</span>
            <span>待审核草案</span>
            <span>一致性终检</span>
          </div>
        </div>

        <div className="product-preview" aria-label="墨铸工作台预览">
          <div className="product-preview-topbar">
            <span className="preview-dot" />
            <span className="preview-dot muted-dot" />
            <span className="preview-dot pale-dot" />
            <strong>《青云山下有剑仙》</strong>
          </div>
          <div className="product-preview-grid">
            <aside className="preview-sidebar">
              <span className="preview-section-title">项目结构</span>
              <div className="preview-row active">第一卷：入山</div>
              <div className="preview-row">剧情单元：剑骨初显</div>
              <div className="preview-row">章节组：1-8 章</div>
              <span className="preview-section-title">资料库</span>
              <div className="preview-chip">角色 12</div>
              <div className="preview-chip">伏笔 7</div>
              <div className="preview-chip">参考资料 5</div>
            </aside>
            <section className="preview-editor">
              <div className="preview-editor-header">
                <span>第 3 章 · 草稿中</span>
                <span>2,846 字</span>
              </div>
              <div className="preview-lines">
                <span />
                <span />
                <span />
                <span className="short-line" />
              </div>
              <div className="preview-agent-card">
                <div>
                  <strong>写作助手</strong>
                  <p>已生成正文草案，等待编辑与校验复审。</p>
                </div>
                <span className="badge badge-warning">待确认</span>
              </div>
            </section>
            <aside className="preview-inspector">
              <span className="preview-section-title">审核链路</span>
              <div className="preview-step done">章节规划</div>
              <div className="preview-step done">章节草案</div>
              <div className="preview-step active">作者确认</div>
              <div className="preview-step">写入作品</div>
              <span className="preview-section-title">终检</span>
              <div className="preview-quality">
                <strong>一致性终检</strong>
                <small>角色 OOC / 世界规则 / 伏笔误用</small>
              </div>
            </aside>
          </div>
        </div>
      </section>

      <section className="marketing-section" id="workflow">
        <div className="marketing-section-heading">
          <div>
            <div className="home-kicker">Workflow</div>
            <h2>首页只讲一件事：作者仍然掌握最终写入权</h2>
          </div>
          <p>
            墨铸的核心不是让模型直接改库，而是把创作协作拆成可追踪、可复审、可确认的流程。
          </p>
        </div>
        <div className="workflow-grid">
          {[
            ["01", "创建作品", "先记录题材、主角、核心卖点和第一章目标，让故事从一开始就有清楚的创作锚点。"],
            ["02", "搭建资料", "维护角色、地点、势力、术语、世界设定、故事背景、参考资料和三层结构化大纲。"],
            ["03", "智能协作", "围绕设定、剧情、写作、校验和编辑建议，让不同创作任务有对应的处理方式。"],
            ["04", "草案审核", "正文、设定、大纲和章节规划等重要变更先成为待审核草案，用户确认后再写入作品。"],
            ["05", "章节终检", "送审章节需要处理一致性终检，检查角色、设定、世界规则、伏笔和剧情逻辑。"],
          ].map(([step, title, description]) => (
            <article className="workflow-card" key={step}>
              <span>{step}</span>
              <h3>{title}</h3>
              <p>{description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="marketing-section">
        <div className="marketing-section-heading">
          <div>
            <div className="home-kicker">Capabilities</div>
            <h2>面向中文小说创作的产品能力</h2>
          </div>
        </div>
        <div className="capability-grid">
          <article>
            <h3>作品规划</h3>
            <p>围绕题材、主角、核心卖点、读者承诺和章节目标建立创作方向，避免只靠临场灵感推进。</p>
          </article>
          <article>
            <h3>结构化大纲</h3>
            <p>用阶段、剧情单元、章节组管理故事结构，让剧情推进、章节安排和后续写作更容易对齐。</p>
          </article>
          <article>
            <h3>文风画像</h3>
            <p>上传 TXT 参考资料生成文风画像，并在小说工作台中选择和应用到作品。</p>
          </article>
          <article>
            <h3>参考资料召回</h3>
            <p>保存素材、设定摘录和外部资料，写作时可以把相关内容作为参考，减少反复翻找。</p>
          </article>
          <article>
            <h3>写作会话恢复</h3>
            <p>围绕具体作品和章节保留写作讨论，重新打开后可以继续处理当前任务和待审核草案。</p>
          </article>
          <article>
            <h3>积分与用量</h3>
            <p>注册赠送 1000 积分，使用 AI 写作能力时可以查看余额和用量记录。</p>
          </article>
        </div>
      </section>

      <section className="marketing-final-cta">
        <div>
          <div className="home-kicker">Start</div>
          <h2>先创建一个作品，再让工作流替你守住边界</h2>
          <p>注册后即可进入工作台，新建小说，并从第一章、创作规划、设定和大纲开始搭建。</p>
        </div>
        {session ? (
          <Link href="/dashboard" className="button marketing-primary-cta">
            进入工作台
          </Link>
        ) : (
          <Link href="/login?mode=register" className="button marketing-primary-cta">
            注册开始写作
          </Link>
        )}
      </section>
    </main>
  );
}
