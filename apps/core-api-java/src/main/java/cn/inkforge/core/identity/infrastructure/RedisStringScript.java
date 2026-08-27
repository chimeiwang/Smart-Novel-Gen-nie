package cn.inkforge.core.identity.infrastructure;

import java.util.List;

@FunctionalInterface
public interface RedisStringScript {

    List<String> eval(String script, List<String> keys, List<String> arguments);
}
