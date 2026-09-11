package cn.inkforge.cli.runtime;

import cn.inkforge.cli.registry.CommandSpec;
import cn.inkforge.cli.transport.CoreApi;
import java.util.List;

/** 单次 CLI 命令的规格、输入、依赖和已认证 Core 客户端。 */
public record CommandContext(
        CommandSpec spec,
        List<String> argv,
        CliDependencies dependencies,
        CoreApi api,
        String profile,
        String origin) {

    /** 返回已认证客户端；登录等无需现有会话的命令不得调用。 */
    public CoreApi requireApi() {
        if (api == null) throw new IllegalStateException("命令缺少已认证 API 客户端");
        return api;
    }
}
