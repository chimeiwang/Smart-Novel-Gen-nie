package cn.inkforge.core.styles.infrastructure;

import static cn.inkforge.core.db.generated.Tables.STYLEREFERENCE;

import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.styles.application.PortraitRunSubmitter;
import cn.inkforge.core.styles.application.StylePortraitRunStarter;
import cn.inkforge.core.styles.domain.PortraitSection;
import cn.inkforge.core.styles.domain.PortraitTaskSnapshot;
import java.util.Objects;
import java.util.function.Supplier;

/** 原无请求体画像入口；一次新请求产生服务器内部 key，跨引擎互斥以锁定的 Style 为准。 */
final class JooqStylePortraitRunStarter implements StylePortraitRunStarter {
    private final CoreDatabase database;
    private final JooqStyleRepository repository;
    private final Supplier<PortraitRunSubmitter> legacySubmitter;
    private final CoreSettings settings;

    JooqStylePortraitRunStarter(CoreDatabase database, JooqStyleRepository repository,
            Supplier<PortraitRunSubmitter> legacySubmitter, CoreSettings settings) {
        this.database = Objects.requireNonNull(database); this.repository = Objects.requireNonNull(repository);
        this.legacySubmitter = Objects.requireNonNull(legacySubmitter);
        this.settings = Objects.requireNonNull(settings);
    }

    @Override
    public PortraitTaskSnapshot start(String userId, String styleId, PortraitSection section) {
        JooqStyleRepository.requireOwnedStyle(database.dsl(), userId, styleId, false);
        if (!settings.v1FreshAgentStartsEnabled()) throw new ApiException(503,
                "AGENT_FRESH_STARTS_DRAINING", "Agent 新建入口正在受控 drain，请稍后重试");
        PortraitRunSubmitter submitter = legacySubmitter.get();
        if (submitter == null) throw unavailable();
        PortraitTaskSnapshot task = repository.createPortraitTask(userId, styleId, section);
        try { submitter.submit(userId, styleId, task.id(), task.id(), section); }
        catch (RuntimeException ignored) {
            // pending 已提交，原 dispatcher 按同一任务继续补投。
        }
        return task;
    }

    private static ApiException unavailable() {
        return new ApiException(503, "PORTRAIT_SERVICE_UNAVAILABLE", "画像生成服务暂时不可用");
    }
}
