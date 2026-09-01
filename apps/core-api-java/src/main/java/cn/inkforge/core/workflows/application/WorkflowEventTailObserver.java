package cn.inkforge.core.workflows.application;

import cn.inkforge.contracts.api.WorkflowEventEnvelope;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.workflows.application.WorkflowEventStreamRepository.EventTailRequest;
import cn.inkforge.core.workflows.application.WorkflowEventStreamRepository.RunKey;
import cn.inkforge.core.workflows.application.WorkflowEventStreamRepository.TailState;
import java.io.IOException;
import java.time.Duration;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * 进程级 V2 Workflow Event tail 观察器。
 *
 * <p>初始 snapshot 仍由每条连接独立读取；snapshot 之后的高水位和 Event tail 按不同 Run 合并查询，再把同一份
 * 不可变事件批次分发给该 Run 的全部连接。PostgreSQL 始终是权威，进程状态只承担有界观察和背压。
 */
public final class WorkflowEventTailObserver implements AutoCloseable {

    private static final Logger LOGGER =
            LoggerFactory.getLogger(WorkflowEventTailObserver.class);
    private static final int MAX_CONSECUTIVE_QUERY_FAILURES = 3;
    private static final int MAX_SUBSCRIBER_QUEUE_CAPACITY = 64;

    private final WorkflowEventStreamRepository repository;
    private final Duration pollInterval;
    private final int eventBatchSize;
    private final int globalConnectionLimit;
    private final int perUserConnectionLimit;
    private final int subscriberQueueCapacity;
    private final int historyLimit;
    private final Object lock = new Object();
    private final Map<RunKey, RunState> runs = new LinkedHashMap<>();
    private final Map<String, Integer> userConnections = new HashMap<>();
    private final Thread worker;

    private boolean running = true;
    private int connectionCount;
    private long wakeVersion;
    private int consecutiveQueryFailures;

    public WorkflowEventTailObserver(
            WorkflowEventStreamRepository repository,
            Duration pollInterval,
            int eventBatchSize,
            int globalConnectionLimit,
            int perUserConnectionLimit,
            int subscriberQueueCapacity) {
        this.repository = Objects.requireNonNull(repository);
        if (pollInterval == null
                || pollInterval.isZero()
                || pollInterval.isNegative()
                || pollInterval.toMillis() < 1
                || eventBatchSize < 1
                || eventBatchSize > 1_000
                || globalConnectionLimit < 1
                || perUserConnectionLimit < 1
                || perUserConnectionLimit > globalConnectionLimit
                || subscriberQueueCapacity < 1
                || subscriberQueueCapacity > MAX_SUBSCRIBER_QUEUE_CAPACITY) {
            throw new IllegalArgumentException("Workflow SSE 共享观察配置无效");
        }
        this.pollInterval = pollInterval;
        this.eventBatchSize = eventBatchSize;
        this.globalConnectionLimit = globalConnectionLimit;
        this.perUserConnectionLimit = perUserConnectionLimit;
        this.subscriberQueueCapacity = subscriberQueueCapacity;
        this.historyLimit = Math.multiplyExact(eventBatchSize, subscriberQueueCapacity);
        this.worker = Thread.ofVirtual()
                .name("workflow-sse-tail-observer")
                .start(this::runSupervised);
    }

    /** 在 snapshot/cursor 已校验后预留连接，并从该原子边界之后开始观察。 */
    public Subscription subscribe(String userId, String runId, long baseSequence) {
        if (baseSequence < 0) {
            throw new IllegalArgumentException("Workflow SSE baseSequence 不能为负数");
        }
        RunKey key = new RunKey(userId, runId);
        synchronized (lock) {
            if (!running) {
                throw new ApiException(
                        503, "WORKFLOW_STREAM_UNAVAILABLE", "工作流事件流暂时不可用");
            }
            int currentUserConnections = userConnections.getOrDefault(userId, 0);
            if (connectionCount >= globalConnectionLimit
                    || currentUserConnections >= perUserConnectionLimit) {
                throw new ApiException(
                        429, "WORKFLOW_STREAM_LIMIT_EXCEEDED", "工作流事件流连接数已达上限");
            }

            RunState state = runs.computeIfAbsent(key, ignored -> new RunState(key, baseSequence));
            Subscription subscription =
                    new Subscription(this, state, baseSequence, subscriberQueueCapacity);
            state.subscribers.add(subscription);
            connectionCount++;
            userConnections.put(userId, currentUserConnections + 1);
            signalWorkerLocked();
            return subscription;
        }
    }

    private void activate(Subscription subscription) throws IOException {
        synchronized (lock) {
            if (subscription.detached) {
                if (subscription.detachFailure != null) {
                    throw subscription.detachFailure;
                }
                throw new IOException("Workflow SSE 订阅已关闭，请重新连接");
            }
            if (subscription.activated) return;
            subscription.activated = true;
            // StreamingResponseBody 已经成功写出 snapshot 后才开始计入慢消费者背压，避免异步线程尚未
            // 获得执行机会时共享 observer 先填满队列并误判断线。
            prepareCatchupLocked(subscription.state, subscription);
            signalWorkerLocked();
        }
    }

    /** 供未来 Redis/本地提交通知只做低延迟唤醒；不携带也不授权任何业务事实。 */
    public void wake() {
        synchronized (lock) {
            signalWorkerLocked();
        }
    }

    int activeConnectionCount() {
        synchronized (lock) {
            return connectionCount;
        }
    }

    int activeRunCount() {
        synchronized (lock) {
            return runs.size();
        }
    }

    private void prepareCatchupLocked(RunState state, Subscription subscription) {
        long baseSequence = subscription.deliveredSequence;
        if (baseSequence < state.fetchCursor) {
            if (!historyCovers(state, baseSequence)) {
                // 仅在极端的 snapshot/注册竞态超过有界历史时回退到共享重读；已有订阅会按 sequence 去重。
                state.fetchCursor = baseSequence;
                return;
            }
            List<WorkflowEventEnvelope> catchup = state.history.stream()
                    .filter(event -> event.getSequence().longValue() > baseSequence)
                    .toList();
            enqueueCatchupLocked(state, subscription, catchup);
            return;
        }
        if (state.tail != null && state.tail.lastEventSequence() >= baseSequence) {
            offerLocked(
                    subscription,
                    new Update(List.of(), state.tail),
                    state.tailGeneration);
        }
    }

    private boolean historyCovers(RunState state, long baseSequence) {
        if (baseSequence >= state.fetchCursor) return true;
        WorkflowEventEnvelope first = state.history.peekFirst();
        return first != null && baseSequence >= first.getSequence().longValue() - 1L;
    }

    private void enqueueCatchupLocked(
            RunState state,
            Subscription subscription,
            List<WorkflowEventEnvelope> events) {
        if (events.isEmpty()) {
            if (state.tail != null) {
                offerLocked(
                        subscription,
                        new Update(List.of(), state.tail),
                        state.tailGeneration);
            }
            return;
        }
        for (int start = 0; start < events.size(); start += eventBatchSize) {
            int end = Math.min(events.size(), start + eventBatchSize);
            boolean last = end == events.size();
            TailState tail = last ? state.tail : null;
            long tailGeneration = last ? state.tailGeneration : subscription.seenTailGeneration;
            if (!offerLocked(
                    subscription,
                    new Update(events.subList(start, end), tail),
                    tailGeneration)) {
                return;
            }
        }
    }

    private void runSupervised() {
        while (true) {
            try {
                runLoop();
                return;
            } catch (RuntimeException exception) {
                LOGGER.atError()
                        .addKeyValue("errorCode", "WORKFLOW_TAIL_OBSERVER_FAILED")
                        .log("Workflow SSE 共享观察循环意外失败，将重新进入监督循环");
                synchronized (lock) {
                    if (!running) return;
                    failAllLocked("WORKFLOW_TAIL_OBSERVER_FAILED", exception);
                    consecutiveQueryFailures = 0;
                }
            }
        }
    }

    private void runLoop() {
        while (true) {
            Cycle cycle;
            synchronized (lock) {
                while (running && runs.isEmpty()) {
                    try {
                        lock.wait();
                    } catch (InterruptedException exception) {
                        if (!running) return;
                    }
                }
                if (!running) return;
                cycle = snapshotCycleLocked();
            }

            observe(cycle);
            synchronized (lock) {
                if (!running) return;
                if (wakeVersion != cycle.wakeVersion()) continue;
                try {
                    lock.wait(pollInterval.toMillis());
                } catch (InterruptedException exception) {
                    if (!running) return;
                }
            }
        }
    }

    private Cycle snapshotCycleLocked() {
        List<CycleRun> values = runs.values().stream()
                .sorted(Comparator.comparing((RunState state) -> state.key.runId())
                        .thenComparing(state -> state.key.userId()))
                .map(state -> new CycleRun(state.key, state, state.fetchCursor))
                .toList();
        return new Cycle(wakeVersion, values);
    }

    private boolean observe(Cycle cycle) {
        final Map<RunKey, TailState> tails;
        try {
            tails = repository.readTails(
                    cycle.runs().stream().map(CycleRun::key).toList());
        } catch (RuntimeException exception) {
            recordQueryFailure(cycle, "WORKFLOW_TAIL_QUERY_FAILED", exception);
            return false;
        }

        List<EventTailRequest> requests = new ArrayList<>();
        synchronized (lock) {
            for (CycleRun observed : cycle.runs()) {
                if (runs.get(observed.key()) != observed.state()) continue;
                TailState tail = tails.get(observed.key());
                if (tail == null || tail.lastEventSequence() < observed.afterSequence()) {
                    failRunLocked(
                            observed.state(),
                            "WORKFLOW_TAIL_INCONSISTENT",
                            null);
                    continue;
                }
                if (tail.lastEventSequence() > observed.afterSequence()) {
                    requests.add(new EventTailRequest(
                            observed.key(),
                            observed.afterSequence(),
                            tail.lastEventSequence()));
                }
            }
        }

        final Map<RunKey, List<WorkflowEventEnvelope>> eventTails;
        try {
            eventTails = requests.isEmpty()
                    ? Map.of()
                    : repository.readEventTails(requests, eventBatchSize);
        } catch (RuntimeException exception) {
            recordQueryFailure(cycle, "WORKFLOW_EVENT_TAIL_QUERY_FAILED", exception);
            return false;
        }

        boolean backlog = false;
        synchronized (lock) {
            for (CycleRun observed : cycle.runs()) {
                RunState state = observed.state();
                if (runs.get(observed.key()) != state) continue;
                TailState tail = tails.get(observed.key());
                if (tail == null) continue;

                List<WorkflowEventEnvelope> events = List.of();
                if (tail.lastEventSequence() > observed.afterSequence()) {
                    // 新连接可能在查询期间要求更早的 catch-up；丢弃这次较新的结果，下轮从新的共享 cursor 重读。
                    if (state.fetchCursor != observed.afterSequence()) {
                        updateTailLocked(state, tail);
                        backlog = true;
                        continue;
                    }
                    events = eventTails.getOrDefault(observed.key(), List.of());
                    if (!validBatch(observed, tail, events)) {
                        failRunLocked(state, "WORKFLOW_EVENT_TAIL_INCONSISTENT", null);
                        continue;
                    }
                    appendHistoryLocked(state, events);
                    state.fetchCursor = events.getLast().getSequence().longValue();
                }

                updateTailLocked(state, tail);
                broadcastLocked(state, events);
                if (runs.get(observed.key()) == state
                        && tail.lastEventSequence() > state.fetchCursor) {
                    backlog = true;
                }
            }
            consecutiveQueryFailures = 0;
        }
        return backlog;
    }

    private static boolean validBatch(
            CycleRun observed,
            TailState tail,
            List<WorkflowEventEnvelope> events) {
        if (events.isEmpty()) return false;
        long expected = observed.afterSequence();
        for (WorkflowEventEnvelope event : events) {
            if (!Objects.equals(event.getRunId(), observed.key().runId())
                    || event.getSequence() == null
                    || event.getSequence().longValue() != expected + 1L
                    || event.getSequence().longValue() > tail.lastEventSequence()) {
                return false;
            }
            expected = event.getSequence().longValue();
        }
        return true;
    }

    private void appendHistoryLocked(
            RunState state, List<WorkflowEventEnvelope> events) {
        for (WorkflowEventEnvelope event : events) {
            state.history.addLast(event);
            while (state.history.size() > historyLimit) state.history.removeFirst();
        }
    }

    private static void updateTailLocked(RunState state, TailState tail) {
        if (!tail.equals(state.tail)) {
            state.tail = tail;
            state.tailGeneration++;
        }
    }

    private void broadcastLocked(
            RunState state, List<WorkflowEventEnvelope> events) {
        for (Subscription subscription : List.copyOf(state.subscribers)) {
            if (!subscription.activated) continue;
            boolean unseenTail = subscription.seenTailGeneration < state.tailGeneration;
            boolean unseenEvent = !events.isEmpty()
                    && events.getLast().getSequence().longValue()
                            > subscription.deliveredSequence;
            if (!unseenTail && !unseenEvent) continue;
            offerLocked(
                    subscription,
                    new Update(events, state.tail),
                    state.tailGeneration);
        }
    }

    private boolean offerLocked(
            Subscription subscription, Update update, long tailGeneration) {
        if (subscription.detached) return false;
        if (subscription.queue.offer(Signal.update(update))) {
            subscription.seenTailGeneration = Math.max(
                    subscription.seenTailGeneration, tailGeneration);
            return true;
        }
        detachLocked(
                subscription,
                new IOException("Workflow SSE 消费速度过慢，请重新连接"));
        return false;
    }

    private void recordQueryFailure(
            Cycle cycle, String errorCode, RuntimeException exception) {
        final int failures;
        synchronized (lock) {
            failures = ++consecutiveQueryFailures;
        }
        LOGGER.atWarn()
                .addKeyValue("errorCode", errorCode)
                .addKeyValue("subscribedRuns", cycle.runs().size())
                .addKeyValue("consecutiveFailures", failures)
                .log("Workflow SSE 共享观察查询失败");
        if (failures < MAX_CONSECUTIVE_QUERY_FAILURES) return;
        synchronized (lock) {
            consecutiveQueryFailures = 0;
            cycle.runs().forEach(observed -> {
                if (runs.get(observed.key()) == observed.state()) {
                    failRunLocked(observed.state(), errorCode, exception);
                }
            });
        }
    }

    private void failAllLocked(String errorCode, Throwable cause) {
        runs.values().stream()
                .flatMap(state -> List.copyOf(state.subscribers).stream())
                .toList()
                .forEach(subscription -> detachLocked(
                        subscription,
                        new IOException("Workflow SSE 共享观察失败：" + errorCode, cause)));
    }

    private void failRunLocked(RunState state, String errorCode, Throwable cause) {
        IOException failure = new IOException("Workflow SSE 共享观察失败：" + errorCode, cause);
        List.copyOf(state.subscribers)
                .forEach(subscription -> detachLocked(subscription, failure));
    }

    private void unsubscribe(Subscription subscription) {
        synchronized (lock) {
            detachLocked(subscription, null);
        }
    }

    private void detachLocked(Subscription subscription, IOException failure) {
        if (subscription.detached) return;
        subscription.detached = true;
        RunState state = subscription.state;
        state.subscribers.remove(subscription);
        connectionCount--;
        userConnections.compute(state.key.userId(), (ignored, count) -> {
            if (count == null || count <= 1) return null;
            return count - 1;
        });
        if (failure != null) {
            subscription.detachFailure = failure;
            subscription.queue.clear();
            subscription.queue.offer(Signal.failure(failure));
        }
        if (state.subscribers.isEmpty()) runs.remove(state.key, state);
        if (runs.isEmpty()) consecutiveQueryFailures = 0;
        signalWorkerLocked();
    }

    private void signalWorkerLocked() {
        wakeVersion++;
        lock.notifyAll();
    }

    @Override
    public void close() {
        synchronized (lock) {
            if (!running) return;
            running = false;
            IOException failure = new IOException("Workflow SSE 服务正在停止");
            runs.values().stream()
                    .flatMap(state -> List.copyOf(state.subscribers).stream())
                    .toList()
                    .forEach(subscription -> detachLocked(subscription, failure));
            lock.notifyAll();
        }
        worker.interrupt();
        try {
            worker.join(Duration.ofSeconds(5).toMillis());
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
        }
    }

    /** 单连接的有界观察句柄；关闭只停止观察，不取消远端 Run。 */
    public static final class Subscription implements AutoCloseable {

        private final WorkflowEventTailObserver owner;
        private final RunState state;
        private final ArrayBlockingQueue<Signal> queue;
        private volatile long deliveredSequence;
        private long seenTailGeneration = -1L;
        private boolean detached;
        private boolean activated;
        private IOException detachFailure;

        private Subscription(
                WorkflowEventTailObserver owner,
                RunState state,
                long baseSequence,
                int queueCapacity) {
            this.owner = owner;
            this.state = state;
            this.deliveredSequence = baseSequence;
            this.queue = new ArrayBlockingQueue<>(queueCapacity);
        }

        /** snapshot 已写入客户端后激活增量观察；重复激活保持幂等。 */
        public Subscription activate() throws IOException {
            owner.activate(this);
            return this;
        }

        public Optional<Update> await(Duration timeout)
                throws IOException, InterruptedException {
            if (timeout == null || timeout.isNegative()) {
                throw new IllegalArgumentException("Workflow SSE 等待时间无效");
            }
            Signal signal = queue.poll(timeout.toNanos(), TimeUnit.NANOSECONDS);
            if (signal == null) return Optional.empty();
            if (signal.failure() != null) throw signal.failure();
            return Optional.of(signal.update());
        }

        public void markDelivered(long sequence) {
            if (sequence < deliveredSequence) {
                throw new IllegalArgumentException("Workflow SSE 已发送序号不能倒退");
            }
            deliveredSequence = sequence;
        }

        @Override
        public void close() {
            owner.unsubscribe(this);
        }
    }

    public record Update(List<WorkflowEventEnvelope> events, TailState tail) {
        public Update {
            events = events == null ? List.of() : List.copyOf(events);
        }
    }

    private static final class RunState {
        private final RunKey key;
        private final List<Subscription> subscribers = new ArrayList<>();
        private final ArrayDeque<WorkflowEventEnvelope> history = new ArrayDeque<>();
        private long fetchCursor;
        private TailState tail;
        private long tailGeneration;

        private RunState(RunKey key, long fetchCursor) {
            this.key = key;
            this.fetchCursor = fetchCursor;
        }
    }

    private record Cycle(long wakeVersion, List<CycleRun> runs) {}

    private record CycleRun(RunKey key, RunState state, long afterSequence) {}

    private record Signal(Update update, IOException failure) {
        private static Signal update(Update value) {
            return new Signal(value, null);
        }

        private static Signal failure(IOException value) {
            return new Signal(null, value);
        }
    }
}
