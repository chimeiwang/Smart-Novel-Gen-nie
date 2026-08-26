package cn.inkforge.cli.commands;

import cn.inkforge.cli.runtime.CommandContext;
import cn.inkforge.cli.transport.CoreApiException;
import cn.inkforge.cli.transport.CoreResponseContractException;
import cn.inkforge.cli.transport.CoreTransportException;

/** 所有轮询观察器共享的单调时钟、指数退避和可重试错误判定。 */
final class WatchSupport {

    static final double UNREACHABLE_TIMEOUT_SECONDS = 300.0;
    private static final double[] BACKOFF_SECONDS = {0.5, 1.0, 2.0, 5.0, 10.0};

    private WatchSupport() {}

    static int sleep(CommandContext context, int index) throws InterruptedException {
        double delay = BACKOFF_SECONDS[Math.min(index, BACKOFF_SECONDS.length - 1)];
        context.dependencies().sleeper().sleep(delay);
        return Math.min(index + 1, BACKOFF_SECONDS.length - 1);
    }

    static boolean retryable(Throwable error, boolean retryContractErrors) {
        if (error instanceof CoreTransportException) return true;
        return error instanceof CoreApiException api
                && api.statusCode() >= 500
                && (retryContractErrors || !(api instanceof CoreResponseContractException));
    }
}
