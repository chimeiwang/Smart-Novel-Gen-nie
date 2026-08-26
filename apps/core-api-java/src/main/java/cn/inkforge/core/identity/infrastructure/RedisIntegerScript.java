package cn.inkforge.core.identity.infrastructure;

import java.util.List;

@FunctionalInterface
public interface RedisIntegerScript {

    List<Long> eval(String script, List<String> keys, List<String> arguments);
}
