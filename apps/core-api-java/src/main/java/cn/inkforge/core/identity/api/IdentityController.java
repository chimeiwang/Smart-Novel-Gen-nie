package cn.inkforge.core.identity.api;

import cn.inkforge.contracts.api.LoginRequest;
import cn.inkforge.contracts.api.RegisterRequest;
import cn.inkforge.contracts.api.UserResponse;
import cn.inkforge.core.generated.api.IdentityApi;
import cn.inkforge.core.identity.application.AuthService;
import cn.inkforge.core.identity.domain.AuthUser;
import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.http.ClientAddressResolver;
import cn.inkforge.core.identity.domain.SessionTokens;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Optional;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RestController;

/** 冻结的四个浏览器认证接口；公共响应永不包含密码哈希或令牌正文。 */
@RestController
public final class IdentityController implements IdentityApi {

    public static final String COOKIE_NAME = "inkforge-token";

    private final Optional<AuthService> configuredService;
    private final CoreSettings settings;
    private final ObjectProvider<HttpServletRequest> requests;

    public IdentityController(
            Optional<AuthService> configuredService,
            CoreSettings settings,
            ObjectProvider<HttpServletRequest> requests) {
        this.configuredService = configuredService;
        this.settings = settings;
        this.requests = requests;
    }

    @Override
    public ResponseEntity<UserResponse> registerApiV1AuthRegisterPost(
            RegisterRequest request) {
        AuthService service = service();
        AuthUser user = service.register(
                request.getUsername(),
                request.getPassword(),
                request.getConfirmPassword(),
                clientIdentity());
        return ResponseEntity.status(201)
                .header(HttpHeaders.SET_COOKIE, sessionCookie(
                        service.createSessionToken(user.id()), service.cookieSecure()))
                .body(response(user));
    }

    @Override
    public ResponseEntity<UserResponse> loginApiV1AuthLoginPost(LoginRequest request) {
        AuthService service = service();
        AuthUser user = service.login(
                request.getUsername(), request.getPassword(), clientIdentity());
        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, sessionCookie(
                        service.createSessionToken(user.id()), service.cookieSecure()))
                .body(response(user));
    }

    @Override
    public ResponseEntity<Void> logoutApiV1AuthLogoutPost() {
        AuthService service = service();
        return ResponseEntity.noContent()
                .header(HttpHeaders.SET_COOKIE, expiredCookie(service.cookieSecure()))
                .build();
    }

    @Override
    public ResponseEntity<UserResponse> meApiV1AuthMeGet(String inkforgeToken) {
        return ResponseEntity.ok(response(service().currentUser(inkforgeToken)));
    }

    private AuthService service() {
        return configuredService.orElseThrow(() ->
                new ApiException(503, "AUTH_UNAVAILABLE", "认证服务暂时不可用"));
    }

    private String clientIdentity() {
        return ClientAddressResolver.resolve(
                requests.getObject(), settings.trustedProxyCidrs());
    }

    private static UserResponse response(AuthUser user) {
        return new UserResponse(
                Long.toString(user.creditBalanceMicros()), user.id(), user.username());
    }

    private static String sessionCookie(String token, boolean secure) {
        return COOKIE_NAME
                + "="
                + token
                + "; HttpOnly; Max-Age="
                + SessionTokens.SESSION_MAX_AGE_SECONDS
                + "; Path=/; SameSite=lax"
                + (secure ? "; Secure" : "");
    }

    private static String expiredCookie(boolean secure) {
        return COOKIE_NAME
                + "=; Expires=Thu, 01 Jan 1970 00:00:00 GMT; HttpOnly; Max-Age=0; Path=/; SameSite=lax"
                + (secure ? "; Secure" : "");
    }
}
