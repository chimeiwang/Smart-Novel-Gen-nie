/**
 * 视频领域的 PostgreSQL、受控文件、FFmpeg 与任务持久化适配器。
 *
 * <p>章节快照、正式镜头、视觉版本、提示词、Take 和后期版本分别保存，不通过可变 Head 改写历史。
 * Agent 与 Seedance 只消费 Core 冻结清单；供应商 URL、轮询状态和进程临时文件都不是正式媒体事实。
 * 历史 {@code VideoScene} 适配器只允许收敛已有任务，不得重新形成公共创建入口。
 */
package cn.inkforge.core.video.infrastructure;
