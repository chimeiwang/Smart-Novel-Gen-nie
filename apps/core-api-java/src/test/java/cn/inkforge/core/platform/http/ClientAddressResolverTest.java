package cn.inkforge.core.platform.http;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.platform.config.CidrBlock;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;

class ClientAddressResolverTest {

    @Test
    void 非可信对端不能伪造真实地址() {
        MockHttpServletRequest request = request("203.0.113.10", "198.51.100.20");

        assertThat(ClientAddressResolver.resolve(request, List.of(CidrBlock.parse("172.16.0.0/12"))))
                .isEqualTo("203.0.113.10");
    }

    @Test
    void 可信代理只接受一份严格真实地址() {
        MockHttpServletRequest valid = request("172.18.0.2", "198.51.100.20");
        MockHttpServletRequest duplicate = request("172.18.0.2", "198.51.100.20");
        duplicate.addHeader("X-Real-IP", "198.51.100.21");
        MockHttpServletRequest multiple = request("172.18.0.2", "198.51.100.20, 10.0.0.1");
        List<CidrBlock> trusted = List.of(CidrBlock.parse("172.16.0.0/12"));

        assertThat(ClientAddressResolver.resolve(valid, trusted)).isEqualTo("198.51.100.20");
        assertThat(ClientAddressResolver.resolve(duplicate, trusted)).isEqualTo("172.18.0.2");
        assertThat(ClientAddressResolver.resolve(multiple, trusted)).isEqualTo("172.18.0.2");
    }

    @Test
    void IPv6必须使用压缩规范形式() {
        MockHttpServletRequest request = request("2001:db8::2", "2001:db8:0:1::9");

        assertThat(ClientAddressResolver.resolve(request, List.of(CidrBlock.parse("2001:db8::/32"))))
                .isEqualTo("2001:db8:0:1::9");
    }

    private MockHttpServletRequest request(String peer, String realIp) {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.setRemoteAddr(peer);
        request.addHeader("X-Real-IP", realIp);
        return request;
    }
}
