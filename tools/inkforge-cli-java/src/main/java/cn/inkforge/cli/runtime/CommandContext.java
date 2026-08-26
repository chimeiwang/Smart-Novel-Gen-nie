package cn.inkforge.cli.runtime;

import cn.inkforge.cli.registry.CommandSpec;
import cn.inkforge.cli.transport.CoreApi;
import java.util.List;

public record CommandContext(
        CommandSpec spec,
        List<String> argv,
        CliDependencies dependencies,
        CoreApi api,
        String profile,
        String origin) {

    public CoreApi requireApi() {
        if (api == null) throw new IllegalStateException("命令缺少已认证 API 客户端");
        return api;
    }
}
