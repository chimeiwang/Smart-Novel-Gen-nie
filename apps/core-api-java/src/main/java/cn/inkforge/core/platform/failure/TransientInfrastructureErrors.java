package cn.inkforge.core.platform.failure;

import cn.inkforge.core.platform.redis.RedisUnavailableException;
import java.io.IOException;
import java.sql.SQLException;
import java.sql.SQLRecoverableException;
import java.sql.SQLTransientException;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

/** 后台 worker 统一识别可重试的连接、事务回滚和基础设施资源错误。 */
public final class TransientInfrastructureErrors {

    private TransientInfrastructureErrors() {}

    public static boolean isTransient(Throwable failure) {
        Set<Throwable> visited = Collections.newSetFromMap(new IdentityHashMap<>());
        Throwable current = failure;
        while (current != null && visited.add(current)) {
            if (current instanceof RedisUnavailableException
                    || current instanceof SQLTransientException
                    || current instanceof SQLRecoverableException
                    || current instanceof IOException) {
                return true;
            }
            if (current instanceof SQLException sql && transientSqlState(sql.getSQLState())) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }

    private static boolean transientSqlState(String state) {
        if (state == null) return false;
        return state.startsWith("08")
                || state.startsWith("40")
                || state.startsWith("53")
                || state.equals("55P03")
                || state.equals("57014")
                || state.equals("57P01")
                || state.equals("57P02")
                || state.equals("57P03");
    }
}
