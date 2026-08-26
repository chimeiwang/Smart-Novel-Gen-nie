package cn.inkforge.core.platform.redis;

import io.lettuce.core.RedisClient;
import io.lettuce.core.RedisFuture;
import io.lettuce.core.RedisURI;
import io.lettuce.core.ClientOptions;
import io.lettuce.core.KeyValue;
import io.lettuce.core.Limit;
import io.lettuce.core.Range;
import io.lettuce.core.SetArgs;
import io.lettuce.core.ScriptOutputType;
import io.lettuce.core.StreamMessage;
import io.lettuce.core.api.StatefulRedisConnection;
import java.net.URI;
import java.time.Duration;
import java.util.Objects;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Core 共用的小型 Lettuce 连接入口。
 *
 * <p>连接按首次命令惰性建立，因此 Redis 暂时不可达不会把 liveness 一并击穿；所有命令有界等待，业务所依赖的
 * 重放与限流操作则失败关闭。该对象不会在字符串或异常中暴露原始连接 URL。
 */
public final class CoreRedis implements AutoCloseable {

    private static final Duration DEFAULT_COMMAND_TIMEOUT = Duration.ofSeconds(1);

    private final RedisClient client;
    private final Duration commandTimeout;
    private final Object connectionLock = new Object();
    private final AtomicBoolean closed = new AtomicBoolean();
    private volatile StatefulRedisConnection<String, String> connection;

    private CoreRedis(RedisClient client, Duration commandTimeout) {
        this.client = client;
        this.commandTimeout = commandTimeout;
    }

    public static CoreRedis connect(String url) {
        validateUrl(url);
        try {
            RedisURI redisUri = RedisURI.create(url);
            redisUri.setTimeout(DEFAULT_COMMAND_TIMEOUT);
            RedisClient client = RedisClient.create(redisUri);
            // 连接失效后由本类在下一条命令时有界重建，禁止后台无限自动重连制造噪声。
            client.setOptions(ClientOptions.builder().autoReconnect(false).build());
            return new CoreRedis(client, DEFAULT_COMMAND_TIMEOUT);
        } catch (RuntimeException exception) {
            throw new IllegalArgumentException("Redis URL 无效");
        }
    }

    public boolean ping() {
        return ping(commandTimeout);
    }

    public boolean ping(Duration timeout) {
        Duration boundedTimeout = positive(timeout, "Redis 探测超时");
        try {
            return "PONG".equals(await(connection().async().ping(), boundedTimeout));
        } catch (RuntimeException exception) {
            invalidateConnection();
            throw new RedisUnavailableException();
        }
    }

    /** 与 Python Redis SET NX EX 保持相同的原子重放消费语义。 */
    public Boolean setIfAbsent(String key, String value, Duration ttl) {
        if (key == null || key.isBlank() || value == null) {
            throw new IllegalArgumentException("Redis 写入参数无效");
        }
        Duration boundedTtl = positive(ttl, "Redis 键有效期");
        if (boundedTtl.toSeconds() < 1) {
            throw new IllegalArgumentException("Redis 键有效期至少为一秒");
        }
        try {
            String result = await(
                    connection().async().set(
                            key,
                            value,
                            new SetArgs().nx().ex(boundedTtl.toSeconds())),
                    commandTimeout);
            return "OK".equals(result);
        } catch (RuntimeException exception) {
            invalidateConnection();
            throw new RedisUnavailableException();
        }
    }

    /** 执行返回整数数组的受控 Lua；用于保持现有认证限流的单次原子决策。 */
    public List<Long> evalIntegers(
            String script, List<String> keys, List<String> arguments) {
        validateScript(script, keys, arguments);
        try {
            RedisFuture<List<Object>> future = connection().async().eval(
                    script,
                    ScriptOutputType.MULTI,
                    keys.toArray(String[]::new),
                    arguments.toArray(String[]::new));
            List<Object> raw = await(future, commandTimeout);
            if (raw == null || raw.size() > 32) {
                throw new RedisUnavailableException();
            }
            List<Long> values = new ArrayList<>(raw.size());
            for (Object value : raw) {
                if (value instanceof Number number) {
                    values.add(number.longValue());
                } else if (value instanceof byte[] bytes) {
                    values.add(Long.parseLong(new String(bytes, java.nio.charset.StandardCharsets.US_ASCII)));
                } else if (value instanceof String text) {
                    values.add(Long.parseLong(text));
                } else {
                    throw new RedisUnavailableException();
                }
            }
            return List.copyOf(values);
        } catch (RuntimeException exception) {
            invalidateConnection();
            throw new RedisUnavailableException();
        }
    }

    /** 执行返回短字符串数组的受控 Lua；写作事件流用它原子校验来源与序号。 */
    public List<String> evalStrings(
            String script, List<String> keys, List<String> arguments) {
        validateScript(script, keys, arguments);
        try {
            RedisFuture<List<Object>> future = connection().async().eval(
                    script,
                    ScriptOutputType.MULTI,
                    keys.toArray(String[]::new),
                    arguments.toArray(String[]::new));
            List<Object> raw = await(future, commandTimeout);
            if (raw == null || raw.size() > 32) throw new RedisUnavailableException();
            List<String> result = new ArrayList<>(raw.size());
            for (Object value : raw) {
                if (value instanceof String text) {
                    result.add(text);
                } else if (value instanceof byte[] bytes) {
                    result.add(new String(bytes, java.nio.charset.StandardCharsets.UTF_8));
                } else if (value instanceof Number number) {
                    result.add(number.toString());
                } else {
                    throw new RedisUnavailableException();
                }
            }
            return List.copyOf(result);
        } catch (RuntimeException exception) {
            invalidateConnection();
            throw new RedisUnavailableException();
        }
    }

    /** 有界读取多个字符串键；缺失项按输入位置返回 null。 */
    public List<String> getMany(List<String> keys) {
        if (keys == null
                || keys.isEmpty()
                || keys.size() > 32
                || keys.stream().anyMatch(key -> key == null || key.isBlank())) {
            throw new IllegalArgumentException("Redis 批量读取参数无效");
        }
        try {
            List<KeyValue<String, String>> values = await(
                    connection().async().mget(keys.toArray(String[]::new)),
                    commandTimeout);
            List<String> result = new ArrayList<>(values.size());
            for (KeyValue<String, String> value : values) {
                result.add(value.hasValue() ? value.getValue() : null);
            }
            return Collections.unmodifiableList(result);
        } catch (RuntimeException exception) {
            invalidateConnection();
            throw new RedisUnavailableException();
        }
    }

    public String get(String key) {
        if (key == null || key.isBlank()) {
            throw new IllegalArgumentException("Redis 读取参数无效");
        }
        try {
            return await(connection().async().get(key), commandTimeout);
        } catch (RuntimeException exception) {
            invalidateConnection();
            throw new RedisUnavailableException();
        }
    }

    /** 读取有界 Redis Stream 范围，保持服务端 ID 顺序和完整字段。 */
    public List<StreamEntry> streamRange(
            String key, String minimum, String maximum, int limit) {
        if (key == null
                || key.isBlank()
                || minimum == null
                || maximum == null
                || limit < 1
                || limit > 10_000) {
            throw new IllegalArgumentException("Redis Stream 读取参数无效");
        }
        try {
            List<StreamMessage<String, String>> messages = await(
                    connection().async().xrange(
                            key, Range.create(minimum, maximum), Limit.from(limit)),
                    commandTimeout);
            List<StreamEntry> result = new ArrayList<>(messages.size());
            for (StreamMessage<String, String> message : messages) {
                result.add(new StreamEntry(
                        message.getId(),
                        Collections.unmodifiableMap(
                                new LinkedHashMap<>(message.getBody()))));
            }
            return List.copyOf(result);
        } catch (RuntimeException exception) {
            invalidateConnection();
            throw new RedisUnavailableException();
        }
    }

    /** 从给定 Stream ID 之后读取；afterExclusive 为 null 时从最早记录开始。 */
    public List<StreamEntry> streamRangeAfter(
            String key, String afterExclusive, int limit) {
        if (key == null
                || key.isBlank()
                || afterExclusive != null && afterExclusive.isBlank()
                || limit < 1
                || limit > 10_000) {
            throw new IllegalArgumentException("Redis Stream 读取参数无效");
        }
        try {
            Range<String> range = afterExclusive == null
                    ? Range.unbounded()
                    : Range.<String>unbounded().gt(afterExclusive);
            List<StreamMessage<String, String>> messages = await(
                    connection().async().xrange(key, range, Limit.from(limit)),
                    commandTimeout);
            List<StreamEntry> result = new ArrayList<>(messages.size());
            for (StreamMessage<String, String> message : messages) {
                result.add(new StreamEntry(
                        message.getId(),
                        Collections.unmodifiableMap(
                                new LinkedHashMap<>(message.getBody()))));
            }
            return List.copyOf(result);
        } catch (RuntimeException exception) {
            invalidateConnection();
            throw new RedisUnavailableException();
        }
    }

    @Override
    public void close() {
        if (!closed.compareAndSet(false, true)) {
            return;
        }
        invalidateConnection();
        client.shutdown(Duration.ZERO, Duration.ofMillis(100));
    }

    @Override
    public String toString() {
        return "CoreRedis[connection=********]";
    }

    private StatefulRedisConnection<String, String> connection() {
        if (closed.get()) {
            throw new RedisUnavailableException();
        }
        StatefulRedisConnection<String, String> current = connection;
        if (current != null && current.isOpen()) {
            return current;
        }
        synchronized (connectionLock) {
            current = connection;
            if (current == null || !current.isOpen()) {
                connection = client.connect();
            }
            return connection;
        }
    }

    private void invalidateConnection() {
        synchronized (connectionLock) {
            StatefulRedisConnection<String, String> current = connection;
            connection = null;
            if (current != null) {
                try {
                    current.close();
                } catch (RuntimeException ignored) {
                    // 连接已失效；关闭阶段不得覆盖原始稳定错误语义。
                }
            }
        }
    }

    private static <T> T await(RedisFuture<T> future, Duration timeout) {
        Objects.requireNonNull(future);
        try {
            return future.get(timeout.toNanos(), TimeUnit.NANOSECONDS);
        } catch (InterruptedException exception) {
            future.cancel(true);
            Thread.currentThread().interrupt();
            throw new RedisUnavailableException();
        } catch (Exception exception) {
            future.cancel(true);
            throw new RedisUnavailableException();
        }
    }

    private static void validateScript(
            String script, List<String> keys, List<String> arguments) {
        if (script == null
                || script.isBlank()
                || keys == null
                || keys.isEmpty()
                || keys.size() > 16
                || keys.stream().anyMatch(key -> key == null || key.isBlank())
                || arguments == null
                || arguments.size() > 32
                || arguments.stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException("Redis Lua 参数无效");
        }
    }

    private static void validateUrl(String value) {
        if (value == null || value.isBlank() || value.indexOf('\0') >= 0) {
            throw new IllegalArgumentException("Redis URL 无效");
        }
        try {
            URI uri = URI.create(value);
            String scheme = uri.getScheme();
            String path = uri.getPath();
            int port = uri.getPort();
            if (!("redis".equals(scheme) || "rediss".equals(scheme))
                    || uri.getHost() == null
                    || uri.getRawQuery() != null
                    || uri.getRawFragment() != null
                    || port == 0
                    || port > 65_535
                    || path != null && !path.isEmpty() && !path.matches("/[0-9]+")) {
                throw new IllegalArgumentException();
            }
        } catch (RuntimeException exception) {
            throw new IllegalArgumentException("Redis URL 无效");
        }
    }

    private static Duration positive(Duration value, String label) {
        if (value == null || value.isZero() || value.isNegative()) {
            throw new IllegalArgumentException(label + "必须大于零");
        }
        return value;
    }

    public record StreamEntry(String id, Map<String, String> fields) {}
}
