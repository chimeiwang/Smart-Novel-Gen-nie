package cn.inkforge.core.identity.api;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.core.CoreApplication;
import cn.inkforge.core.identity.application.AuthRepository;
import cn.inkforge.core.identity.application.AuthService;
import cn.inkforge.core.identity.domain.AuthUser;
import cn.inkforge.core.identity.domain.DuplicateUsernameException;
import cn.inkforge.core.identity.domain.PasswordCodec;
import cn.inkforge.core.identity.infrastructure.Hs256SessionTokens;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Clock;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;

@SpringBootTest(
        classes = CoreApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Import(IdentityApiTest.TestIdentityConfiguration.class)
class IdentityApiTest {

    @LocalServerPort
    private int port;

    private final HttpClient client = HttpClient.newHttpClient();

    @Test
    void 注册登录当前用户与退出必须保持完整HTTP契约() throws Exception {
        HttpResponse<String> registration = post(
                "/api/v1/auth/register",
                "{\"username\":\"  Alice_1  \",\"password\":\"密码1234\",\"confirmPassword\":\"密码1234\"}",
                null);

        assertThat(registration.statusCode()).isEqualTo(201);
        assertThat(registration.body()).contains(
                "\"id\":\"user-new\"",
                "\"username\":\"alice_1\"",
                "\"creditBalanceMicros\":\"1000000000\"");
        String setCookie = registration.headers().firstValue("set-cookie").orElseThrow();
        assertThat(setCookie).contains(
                "inkforge-token=",
                "HttpOnly",
                "Max-Age=2592000",
                "Path=/",
                "SameSite=lax");
        assertThat(setCookie).doesNotContain("Secure");
        String cookie = setCookie.substring(0, setCookie.indexOf(';'));

        HttpResponse<String> me = get("/api/v1/auth/me", cookie);
        assertThat(me.statusCode()).isEqualTo(200);
        assertThat(me.body()).contains("\"username\":\"alice_1\"");

        HttpResponse<String> login = post(
                "/api/v1/auth/login",
                "{\"username\":\" ALICE_1 \",\"password\":\"密码1234\"}",
                null);
        assertThat(login.statusCode()).isEqualTo(200);
        assertThat(login.headers().firstValue("set-cookie")).isPresent();

        HttpResponse<String> invalid = post(
                "/api/v1/auth/login",
                "{\"username\":\"alice_1\",\"password\":\"错误密码\"}",
                null);
        assertThat(invalid.statusCode()).isEqualTo(401);
        assertThat(invalid.body()).contains(
                "\"code\":\"INVALID_CREDENTIALS\"",
                "\"message\":\"用户名或密码错误\"");
        assertThat(invalid.headers().firstValue("set-cookie")).isEmpty();

        HttpResponse<String> logout = post("/api/v1/auth/logout", "", cookie);
        assertThat(logout.statusCode()).isEqualTo(204);
        assertThat(logout.headers().firstValue("set-cookie").orElseThrow())
                .contains("inkforge-token=", "Max-Age=0", "Path=/", "HttpOnly", "SameSite=lax");
    }

    @Test
    void 输入上界未知字段和重名不得设置Cookie() throws Exception {
        HttpResponse<String> extra = post(
                "/api/v1/auth/login",
                "{\"username\":\"alice\",\"password\":\"123456\",\"unknown\":true}",
                null);
        assertThat(extra.statusCode()).isEqualTo(422);
        assertThat(extra.body()).contains("\"type\":\"extra_forbidden\"");

        String oversized = "a".repeat(4097);
        HttpResponse<String> tooLarge = post(
                "/api/v1/auth/login",
                "{\"username\":\"alice\",\"password\":\"" + oversized + "\"}",
                null);
        assertThat(tooLarge.statusCode()).isEqualTo(422);
        assertThat(tooLarge.body()).contains("\"type\":\"string_too_long\"");
        assertThat(tooLarge.headers().firstValue("set-cookie")).isEmpty();
    }

    private HttpResponse<String> post(String path, String body, String cookie) throws Exception {
        HttpRequest.Builder request = HttpRequest.newBuilder(uri(path))
                .header("X-Request-ID", "identity-api-test");
        if (!body.isEmpty()) {
            request.header("Content-Type", "application/json");
        }
        if (cookie != null) {
            request.header("Cookie", cookie);
        }
        return client.send(
                request.POST(HttpRequest.BodyPublishers.ofString(body)).build(),
                HttpResponse.BodyHandlers.ofString());
    }

    private HttpResponse<String> get(String path, String cookie) throws Exception {
        return client.send(
                HttpRequest.newBuilder(uri(path)).header("Cookie", cookie).GET().build(),
                HttpResponse.BodyHandlers.ofString());
    }

    private URI uri(String path) {
        return URI.create("http://127.0.0.1:" + port + path);
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class TestIdentityConfiguration {

        @Bean
        AuthService testAuthService() {
            FakeRepository repository = new FakeRepository();
            PasswordCodec passwords = new PasswordCodec() {
                @Override
                public String hash(String password) {
                    return "hash:" + password;
                }

                @Override
                public boolean matches(String password, String passwordHash) {
                    return passwordHash.equals("hash:" + password);
                }
            };
            return new AuthService(
                    repository,
                    (action, clientIdentity, username) -> {},
                    passwords,
                    new Hs256SessionTokens("测试专用会话密钥-长度足够", Clock.systemUTC()),
                    false);
        }
    }

    private static final class FakeRepository implements AuthRepository {
        private final Map<String, AuthUser> names = new HashMap<>();
        private final Map<String, AuthUser> ids = new HashMap<>();

        @Override
        public AuthUser findByUsername(String username) {
            return names.get(username);
        }

        @Override
        public AuthUser findById(String userId) {
            return ids.get(userId);
        }

        @Override
        public AuthUser register(String username, String passwordHash) {
            if (names.containsKey(username)) {
                throw new DuplicateUsernameException();
            }
            AuthUser user = new AuthUser("user-new", username, passwordHash, 1_000_000_000L);
            names.put(username, user);
            ids.put(user.id(), user);
            return user;
        }
    }
}
