package cn.inkforge.core.references.infrastructure;

import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.references.application.ReferenceRepository;
import java.time.Clock;

/** 跨模块事务测试使用真实参考资料仓储，不改变生产实现的包可见性。 */
public final class ReferenceRepositoryTestFactory {
    private ReferenceRepositoryTestFactory() {}

    public static ReferenceRepository create(CoreDatabase database, CuidV1Generator ids, Clock clock) {
        return new JooqReferenceRepository(database, ids, clock);
    }
}
