package cn.inkforge.core.workflows.application;

import cn.inkforge.contracts.api.WorkflowEventEnvelope;
import cn.inkforge.core.platform.db.DatabaseQueryCancellation;
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
import java.util.concurrent.Callable;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.FutureTask;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;
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
    private final WorkflowEventObserverTimeouts timeouts;
    private final Object lock = new Object();
    private final Object queryLock = new Object();
    private final Map<RunKey, RunState> runs = new LinkedHashMap<>();
    private final Map<String, Integer> userConnections = new HashMap<>();
    private final ExecutorService queryExecutor;
    private final AtomicInteger activeQueries = new AtomicInteger();
    private final Thread worker;

    private volatile boolean running = true;
    private QueryExecution<?> currentQuery;
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
        this(
                repository,
                pollInterval,
                eventBatchSize,
                globalConnectionLimit,
                perUserConnectionLimit,
                subscriberQueueCapacity,
                WorkflowEventObserverTimeouts.productionDefaults());
    }

    public WorkflowEventTailObserver(
            WorkflowEventStreamRepository repository,
            Duration pollInterval,
            int eventBatchSize,
            int globalConnectionLimit,
            int perUserConnectionLimit,
            int subscriberQueueCapacity,
            WorkflowEventObserverTimeouts timeouts) {
        this(
                repository,
                pollInterval,
                eventBatchSize,
                globalConnectionLimit,
                perUserConnectionLimit,
                subscriberQueueCapacity,
                timeouts,
                null);
    }

    WorkflowEventTailObserver(
            WorkflowEventStreamRepository repository,
            Duration pollInterval,
            int eventBatchSize,
            int globalConnectionLimit,
            int perUserConnectionLimit,
            int subscriberQueueCapacity,
            WorkflowEventObserverTimeouts timeouts,
            ExecutorService queryExecutor) {
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
        this.timeouts = Objects.requireNonNull(timeouts);
        this.queryExecutor = queryExecutor == null
                ? Executors.newSingleThreadExecutor(
                        Thread.ofVirtual().name("workflow-sse-tail-query").factory())
                : queryExecutor;
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
            // SseEmitter 已经成功发送 snapshot 后才开始计入慢消费者背压，避免连接 worker 尚未
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

    int activeQueryCount() {
        return activeQueries.get();
    }

    boolean workerAlive() {
        return worker.isAlive();
    }

    boolean queryExecutorTerminated() {
        return queryExecutor.isTerminated();
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
            } catch (ObserverStoppingException exception) {
                return;
            } catch (QueryTerminationFailedException exception) {
                LOGGER.atError()
                        .addKeyValue("errorCode", "WORKFLOW_TAIL_QUERY_UNCANCELLABLE")
                        .addKeyValue("queryPhase", exception.queryPhase())
                        .addKeyValue("elapsedMillis", exception.elapsedMillis())
                        .addKeyValue("statementCancelRequested", true)
                        .addKeyValue("connectionAbortRequested", true)
                        .log("Workflow SSE 共享查询无法在硬中止后退出，永久停止 observer");
                synchronized (lock) {
                    running = false;
                    failAllLocked("WORKFLOW_TAIL_QUERY_UNCANCELLABLE", exception);
                    consecutiveQueryFailures = 0;
                    lock.notifyAll();
                }
                queryExecutor.shutdownNow();
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
            List<RunKey> keys = cycle.runs().stream().map(CycleRun::key).toList();
            tails = executeQuery(
                    "read_tails", cancellation -> repository.readTails(keys, cancellation));
        } catch (QueryTerminationFailedException | ObserverStoppingException exception) {
            throw exception;
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
                    : executeQuery(
                            "read_event_tails",
                            cancellation -> repository.readEventTails(
                                    requests, eventBatchSize, cancellation));
        } catch (QueryTerminationFailedException | ObserverStoppingException exception) {
            throw exception;
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

    private <T> T executeQuery(
            String queryPhase,
            Function<DatabaseQueryCancellation, T> operation) {
        QueryExecution<T> execution = new QueryExecution<>(queryPhase);
        synchronized (queryLock) {
            if (!running) throw new ObserverStoppingException();
            if (currentQuery != null) {
                throw new IllegalStateException("Workflow SSE observer 查询不得重叠");
            }
            try {
                QueryFutureTask<T> task = execution.newTask(() -> {
                    activeQueries.incrementAndGet();
                    try {
                        return operation.apply(execution.cancellation);
                    } finally {
                        activeQueries.decrementAndGet();
                        // FutureTask 会先发布终态并唤醒 get()，再执行 done/run finally。
                        // 完成门必须在 callable 返回前关闭，否则 observer 可能在这个窗口
                        // 保留旧 currentQuery，并把下一次顺序 tail 查询误判为重叠。
                        execution.finishOnce();
                    }
                });
                execution.future = task;
                currentQuery = execution;
                queryExecutor.execute(task);
            } catch (RejectedExecutionException exception) {
                execution.finishOnce();
                if (currentQuery == execution) currentQuery = null;
                if (!running) throw new ObserverStoppingException();
                throw new IllegalStateException("Workflow SSE observer 查询执行器不可用", exception);
            }
        }

        try {
            return execution.future.get(
                    timeouts.wallClockTimeout().toNanos(), TimeUnit.NANOSECONDS);
        } catch (TimeoutException exception) {
            CancellationOutcome outcome = cancelAndAwait(execution, false);
            long elapsedMillis = execution.elapsedMillis();
            if (!outcome.terminated()) {
                throw new QueryTerminationFailedException(queryPhase, elapsedMillis, exception);
            }
            throw new BoundedQueryFailureException(
                    queryPhase,
                    elapsedMillis,
                    true,
                    outcome.connectionAbortRequested(),
                    exception);
        } catch (InterruptedException exception) {
            CancellationOutcome outcome = cancelAndAwait(execution, true);
            long elapsedMillis = execution.elapsedMillis();
            if (!outcome.terminated()) {
                throw new QueryTerminationFailedException(queryPhase, elapsedMillis, exception);
            }
            if (!running) throw new ObserverStoppingException();
            throw new BoundedQueryFailureException(
                    queryPhase,
                    elapsedMillis,
                    true,
                    outcome.connectionAbortRequested(),
                    exception);
        } catch (CancellationException exception) {
            CancellationOutcome outcome = cancelAndAwait(execution, false);
            long elapsedMillis = execution.elapsedMillis();
            if (!outcome.terminated()) {
                throw new QueryTerminationFailedException(queryPhase, elapsedMillis, exception);
            }
            if (!running) throw new ObserverStoppingException();
            throw new BoundedQueryFailureException(
                    queryPhase,
                    elapsedMillis,
                    true,
                    outcome.connectionAbortRequested(),
                    exception);
        } catch (ExecutionException exception) {
            Throwable cause = exception.getCause();
            if (cause instanceof Error error) throw error;
            throw new BoundedQueryFailureException(
                    queryPhase,
                    execution.elapsedMillis(),
                    execution.cancellation.cancellationRequested(),
                    false,
                    cause);
        } finally {
            clearCompletedQuery(execution);
        }
    }

    private CancellationOutcome cancelAndAwait(
            QueryExecution<?> execution, boolean restoreInterrupt) {
        execution.cancellation.requestStatementCancel();
        execution.future.cancel(true);
        logCancellationFailure(execution);
        WaitResult statementWait = awaitFinished(
                execution.finished, timeouts.statementCancelGrace());
        boolean interrupted = restoreInterrupt || statementWait.interrupted();
        if (statementWait.finished()) {
            if (interrupted) Thread.currentThread().interrupt();
            return new CancellationOutcome(true, false);
        }

        execution.cancellation.requestConnectionAbort();
        logCancellationFailure(execution);
        WaitResult abortWait = awaitFinished(
                execution.finished, timeouts.connectionAbortGrace());
        interrupted = interrupted || abortWait.interrupted();
        if (interrupted) Thread.currentThread().interrupt();
        return new CancellationOutcome(abortWait.finished(), true);
    }

    private void logCancellationFailure(QueryExecution<?> execution) {
        execution.cancellation.cancellationFailure().ifPresent(exception -> {
            if (!execution.cancellationFailureLogged.compareAndSet(false, true)) return;
            LOGGER.atError()
                    .addKeyValue("errorCode", "WORKFLOW_TAIL_QUERY_CANCEL_ACTION_FAILED")
                    .addKeyValue("queryPhase", execution.queryPhase)
                    .addKeyValue("exceptionType", exception.getClass().getName())
                    .setCause(exception)
                    .log("Workflow SSE observer 数据库取消动作失败");
        });
    }

    private static WaitResult awaitFinished(CountDownLatch finished, Duration timeout) {
        long deadline = System.nanoTime() + timeout.toNanos();
        boolean interrupted = false;
        while (finished.getCount() != 0L) {
            long remaining = deadline - System.nanoTime();
            if (remaining <= 0L) return new WaitResult(false, interrupted);
            try {
                if (finished.await(remaining, TimeUnit.NANOSECONDS)) {
                    return new WaitResult(true, interrupted);
                }
            } catch (InterruptedException exception) {
                interrupted = true;
            }
        }
        return new WaitResult(true, interrupted);
    }

    private void clearCompletedQuery(QueryExecution<?> execution) {
        if (execution.finished.getCount() != 0L) return;
        synchronized (queryLock) {
            if (currentQuery == execution) currentQuery = null;
        }
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
        BoundedQueryFailureException bounded = exception instanceof BoundedQueryFailureException value
                ? value
                : null;
        LOGGER.atWarn()
                .addKeyValue("errorCode", errorCode)
                .addKeyValue(
                        "failureClass",
                        bounded != null && bounded.wallClockExpired()
                                ? "wall_clock_timeout"
                                : "query_failed")
                .addKeyValue("queryPhase", bounded == null ? "unknown" : bounded.queryPhase())
                .addKeyValue(
                        "wallClockTimeoutMillis", timeouts.wallClockTimeout().toMillis())
                .addKeyValue("elapsedMillis", bounded == null ? -1L : bounded.elapsedMillis())
                .addKeyValue(
                        "statementCancelRequested",
                        bounded != null && bounded.statementCancelRequested())
                .addKeyValue(
                        "connectionAbortRequested",
                        bounded != null && bounded.connectionAbortRequested())
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
            running = false;
            IOException failure = new IOException("Workflow SSE 服务正在停止");
            runs.values().stream()
                    .flatMap(state -> List.copyOf(state.subscribers).stream())
                    .toList()
                    .forEach(subscription -> detachLocked(subscription, failure));
            lock.notifyAll();
        }

        synchronized (queryLock) {
            if (currentQuery != null) {
                currentQuery.cancellation.requestStatementCancel();
                currentQuery.cancellation.requestConnectionAbort();
                if (currentQuery.future != null) currentQuery.future.cancel(true);
                logCancellationFailure(currentQuery);
            }
            queryExecutor.shutdownNow();
        }
        worker.interrupt();

        ShutdownResult shutdown = awaitShutdown();
        if (shutdown.interrupted()) Thread.currentThread().interrupt();
        if (shutdown.interrupted()
                || worker.isAlive()
                || !queryExecutor.isTerminated()
                || activeQueries.get() != 0) {
            LOGGER.atError()
                    .addKeyValue("errorCode", "WORKFLOW_TAIL_OBSERVER_SHUTDOWN_INCOMPLETE")
                    .addKeyValue("workerAlive", worker.isAlive())
                    .addKeyValue("queryExecutorTerminated", queryExecutor.isTerminated())
                    .addKeyValue("activeQueries", activeQueries.get())
                    .addKeyValue("interrupted", shutdown.interrupted())
                    .log("Workflow SSE observer 未在期限内停止");
            throw new IllegalStateException("Workflow SSE observer 未在期限内停止");
        }
    }

    private ShutdownResult awaitShutdown() {
        long deadline = System.nanoTime() + timeouts.shutdownTimeout().toNanos();
        boolean interrupted = false;
        while (worker.isAlive()) {
            long remaining = deadline - System.nanoTime();
            if (remaining <= 0L) break;
            try {
                long millis = Math.max(1L, TimeUnit.NANOSECONDS.toMillis(remaining));
                worker.join(millis);
            } catch (InterruptedException exception) {
                interrupted = true;
            }
        }
        while (!queryExecutor.isTerminated()) {
            long remaining = deadline - System.nanoTime();
            if (remaining <= 0L) break;
            try {
                queryExecutor.awaitTermination(remaining, TimeUnit.NANOSECONDS);
            } catch (InterruptedException exception) {
                interrupted = true;
            }
        }
        return new ShutdownResult(interrupted);
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

    private record CancellationOutcome(
            boolean terminated, boolean connectionAbortRequested) {}

    private record WaitResult(boolean finished, boolean interrupted) {}

    private record ShutdownResult(boolean interrupted) {}

    private static final class QueryExecution<T> {

        private final String queryPhase;
        private final long startedNanos = System.nanoTime();
        private final DatabaseQueryCancellation cancellation = new DatabaseQueryCancellation();
        private final CountDownLatch finished = new CountDownLatch(1);
        private final AtomicBoolean finishedOnce = new AtomicBoolean();
        private final AtomicBoolean cancellationFailureLogged = new AtomicBoolean();
        private Future<T> future;

        private QueryExecution(String queryPhase) {
            this.queryPhase = queryPhase;
        }

        private long elapsedMillis() {
            return TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - startedNanos);
        }

        private QueryFutureTask<T> newTask(Callable<T> callable) {
            return new QueryFutureTask<>(callable, this);
        }

        private void finishOnce() {
            if (finishedOnce.compareAndSet(false, true)) finished.countDown();
        }
    }

    /**
     * Future.cancel 可能发生在 executor 真正调用 run 之前。done 只在任务尚未进入 run 时证明它不会再执行；
     * 一旦 run 已进入，必须等 run finally，不能把 Future 的 cancelled 状态冒充原查询线程已退出。
     */
    private static final class QueryFutureTask<T> extends FutureTask<T> {

        private final QueryExecution<T> execution;
        private final AtomicBoolean runEntered = new AtomicBoolean();

        private QueryFutureTask(Callable<T> callable, QueryExecution<T> execution) {
            super(callable);
            this.execution = execution;
        }

        @Override
        public void run() {
            runEntered.set(true);
            try {
                super.run();
            } finally {
                execution.finishOnce();
            }
        }

        @Override
        protected void done() {
            if (!isCancelled() || !runEntered.get()) execution.finishOnce();
        }
    }

    private static class BoundedQueryFailureException extends RuntimeException {

        private final String queryPhase;
        private final long elapsedMillis;
        private final boolean statementCancelRequested;
        private final boolean connectionAbortRequested;

        private BoundedQueryFailureException(
                String queryPhase,
                long elapsedMillis,
                boolean statementCancelRequested,
                boolean connectionAbortRequested,
                Throwable cause) {
            super("工作流事件观察查询失败", cause);
            this.queryPhase = queryPhase;
            this.elapsedMillis = elapsedMillis;
            this.statementCancelRequested = statementCancelRequested;
            this.connectionAbortRequested = connectionAbortRequested;
        }

        final String queryPhase() {
            return queryPhase;
        }

        final long elapsedMillis() {
            return elapsedMillis;
        }

        private boolean statementCancelRequested() {
            return statementCancelRequested;
        }

        private boolean connectionAbortRequested() {
            return connectionAbortRequested;
        }

        private boolean wallClockExpired() {
            return getCause() instanceof TimeoutException;
        }
    }

    private static final class QueryTerminationFailedException
            extends BoundedQueryFailureException {

        private QueryTerminationFailedException(
                String queryPhase, long elapsedMillis, Throwable cause) {
            super(queryPhase, elapsedMillis, true, true, cause);
        }
    }

    private static final class ObserverStoppingException extends RuntimeException {}

    private record Signal(Update update, IOException failure) {
        private static Signal update(Update value) {
            return new Signal(value, null);
        }

        private static Signal failure(IOException value) {
            return new Signal(null, value);
        }
    }
}
