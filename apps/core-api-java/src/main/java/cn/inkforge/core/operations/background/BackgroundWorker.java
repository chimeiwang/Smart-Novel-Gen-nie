package cn.inkforge.core.operations.background;

/** 可被监督器独占运行并协作停止的后台工作者。 */
public interface BackgroundWorker {

    /** 持续运行直到收到停止请求；正常返回也会被视为意外退出。 */
    void run() throws Exception;

    /** 发出幂等停止请求，不能在此方法中等待工作线程结束。 */
    void requestStop();
}
