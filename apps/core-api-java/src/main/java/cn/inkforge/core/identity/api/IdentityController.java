package cn.inkforge.core.identity.api;

import cn.inkforge.contracts.api.CreatePhoneChallengeRequest;
import cn.inkforge.contracts.api.LoginRequest;
import cn.inkforge.contracts.api.PhoneChallengeResponse;
import cn.inkforge.contracts.api.PhoneLoginResponse;
import cn.inkforge.contracts.api.RegisterRequest;
import cn.inkforge.contracts.api.UserResponse;
import cn.inkforge.contracts.api.VerifyPhoneChallengeRequest;
import cn.inkforge.core.generated.api.IdentityApi;
import cn.inkforge.core.identity.application.AuthService;
import cn.inkforge.core.identity.application.PhoneAuthService;
import cn.inkforge.core.identity.application.PhoneChallengeReceipt;
import cn.inkforge.core.identity.application.PhoneLoginResult;
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

/** 浏览器认证接口；公共响应永不包含完整手机号、密码哈希或令牌正文。 */
@RestController
public final class IdentityController implements IdentityApi {

    public static final String COOKIE_NAME = "inkforge-token";

    private final Optional<AuthService> configuredService;
    private final Optional<PhoneAuthService> configuredPhoneService;
    private final CoreSettings settings;
    private final ObjectProvider<HttpServletRequest> requests;

    public IdentityController(
            Optional<AuthService> configuredService,
            Optional<PhoneAuthService> configuredPhoneService,
            CoreSettings settings,
            ObjectProvider<HttpServletRequest> requests) {
        this.configuredService = configuredService;
        this.configuredPhoneService = configuredPhoneService;
        this.settings = settings;
        this.requests = requests;
    }

    @Override
    public ResponseEntity<PhoneChallengeResponse>
            createPhoneChallengeApiV1AuthPhoneChallengesPost(
                    CreatePhoneChallengeRequest request) {
        PhoneChallengeReceipt receipt = phoneService().createChallenge(
                request.getPhone(),
                request.getCaptchaVerifyParam(),
                request.getConsentVersion(),
                Boolean.TRUE.equals(request.getAcceptedTerms()),
                request.getClientRequestId(),
                clientIdentity());
        return ResponseEntity.status(201).body(new PhoneChallengeResponse(
                receipt.challengeId(),
                receipt.expiresInSeconds(),
                receipt.resendAfterSeconds()));
    }

    @Override
    public ResponseEntity<UserResponse> registerApiV1AuthRegisterPost(
            RegisterRequest request) {
        if (!settings.usernameRegistrationEnabled()) {
            throw new ApiException(
                    404, "USERNAME_REGISTRATION_DISABLED", "用户名注册入口已关闭");
        }
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
    public ResponseEntity<PhoneLoginResponse>
            verifyPhoneChallengeApiV1AuthPhoneChallengesChallengeIdVerifyPost(
                    String challengeId, VerifyPhoneChallengeRequest request) {
        PhoneLoginResult result = phoneService().verifyChallenge(
                challengeId,
                request.getPhone(),
                request.getCode(),
                request.getClientRequestId());
        AuthService auth = service();
        AuthUser user = result.user();
        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, sessionCookie(
                        auth.createSessionToken(user.id()), auth.cookieSecure()))
                .body(new PhoneLoginResponse(
                        Long.toString(user.creditBalanceMicros()),
                        user.id(),
                        result.newUser(),
                        result.maskedPhone(),
                        user.username()));
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

    private PhoneAuthService phoneService() {
        return configuredPhoneService.orElseThrow(() ->
                new ApiException(503, "PHONE_AUTH_UNAVAILABLE", "手机号认证暂时不可用"));
    }

    private String clientIdentity() {
        return ClientAddressResolver.resolve(
                requests.getObject(), settings.trustedProxyCidrs());
    }

    private static UserResponse response(AuthUser user) {
        UserResponse response = new UserResponse(
                Long.toString(user.creditBalanceMicros()), user.id(), user.username());
        response.setMaskedPhone(user.maskedPhone());
        return response;
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
