package cn.inkforge.core.agentgateway;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.http.HttpClient;
import org.junit.jupiter.api.Test;

class AgentGatewayConfigurationTest {

    @Test
    void Agent专用客户端必须固定HTTP1_1以兼容Uvicorn() {
        HttpClient client = new AgentGatewayConfiguration().agentHttpClient();

        assertThat(client.version()).isEqualTo(HttpClient.Version.HTTP_1_1);
    }
}
