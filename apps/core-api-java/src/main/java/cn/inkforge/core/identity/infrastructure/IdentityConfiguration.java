package cn.inkforge.core.identity.infrastructure;

import cn.inkforge.core.identity.application.AuthRateLimiter;
import cn.inkforge.core.identity.application.AuthRepository;
import cn.inkforge.core.identity.application.AuthService;
import cn.inkforge.core.identity.application.PhoneAuthRateLimiter;
import cn.inkforge.core.identity.application.PhoneAuthRepository;
import cn.inkforge.core.identity.application.PhoneAuthService;
import cn.inkforge.core.identity.application.PhoneCaptchaVerifier;
import cn.inkforge.core.identity.application.PhoneChallengeStore;
import cn.inkforge.core.identity.application.PhoneIdentityDigester;
import cn.inkforge.core.identity.application.PhoneSmsProvider;
import cn.inkforge.core.identity.domain.PasswordCodec;
import cn.inkforge.core.identity.domain.SessionTokens;
import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.redis.CoreRedis;
import java.time.Clock;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class IdentityConfiguration {

    @Bean
    PasswordCodec passwordCodec() {
        return new BCryptPasswordCodec();
    }

    @Bean
    @ConditionalOnProperty(name = "DATABASE_URL")
    AuthRepository authRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            CoreSettings settings) {
        return new JooqAuthRepository(
                database,
                ids,
                coreClock,
                settings.phoneAuthEnabled() && settings.phoneAuthSendEnabled());
    }

    @Bean
    @ConditionalOnProperty(name = "REDIS_URL")
    AuthRateLimiter authRateLimiter(CoreRedis redis) {
        return new RedisAuthRateLimiter(redis::evalIntegers, "auth:limit:");
    }

    @Bean
    @ConditionalOnProperty(name = "JWT_SECRET")
    SessionTokens sessionTokens(CoreSettings settings, Clock coreClock) {
        return new Hs256SessionTokens(settings.jwtSecret().reveal(), coreClock);
    }

    @Bean
    @ConditionalOnProperty(name = {"DATABASE_URL", "REDIS_URL", "JWT_SECRET"})
    AuthService authService(
            AuthRepository repository,
            AuthRateLimiter rateLimiter,
            PasswordCodec passwordCodec,
            SessionTokens sessionTokens,
            CoreSettings settings) {
        return new AuthService(
                repository,
                rateLimiter,
                passwordCodec,
                sessionTokens,
                settings.sessionCookieSecure());
    }

    @Bean
    @ConditionalOnProperty(
            name = {"PHONE_AUTH_ENABLED", "PHONE_AUTH_SEND_ENABLED"},
            havingValue = "true")
    PhoneIdentityDigester phoneIdentityDigester(CoreSettings settings) {
        return new HmacSha256PhoneIdentityDigester(
                settings.phoneAuthHmacSecret().reveal());
    }

    @Bean
    @ConditionalOnProperty(
            name = {"PHONE_AUTH_ENABLED", "PHONE_AUTH_SEND_ENABLED"},
            havingValue = "true")
    PhoneAuthRateLimiter phoneAuthRateLimiter(
            CoreRedis redis,
            CoreSettings settings,
            PhoneIdentityDigester digester) {
        return new RedisPhoneAuthRateLimiter(
                redis::evalIntegers,
                settings.phoneAuthRedisPrefix() + "limit:",
                digester);
    }

    @Bean
    @ConditionalOnProperty(
            name = {"PHONE_AUTH_ENABLED", "PHONE_AUTH_SEND_ENABLED"},
            havingValue = "true")
    PhoneChallengeStore phoneChallengeStore(CoreRedis redis, CoreSettings settings) {
        return new RedisPhoneChallengeStore(
                redis::evalStrings, settings.phoneAuthRedisPrefix() + "challenge-state:");
    }

    @Bean
    @ConditionalOnProperty(
            name = {"PHONE_AUTH_ENABLED", "PHONE_AUTH_SEND_ENABLED"},
            havingValue = "true")
    PhoneAuthRepository phoneAuthRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            PasswordCodec passwords) {
        return new JooqPhoneAuthRepository(database, ids, coreClock, passwords);
    }

    @Bean
    @ConditionalOnProperty(
            name = {"PHONE_AUTH_ENABLED", "PHONE_AUTH_SEND_ENABLED"},
            havingValue = "true")
    PhoneSmsProvider phoneSmsProvider(CoreSettings settings) throws Exception {
        com.aliyun.teaopenapi.models.Config config = aliyunConfig(
                settings, "dypnsapi.aliyuncs.com");
        return new AliyunPhoneSmsProvider(
                new com.aliyun.dypnsapi20170525.Client(config),
                settings.aliyunPnvsSignName(),
                settings.aliyunPnvsTemplateCode(),
                settings.aliyunPnvsSchemeName());
    }

    @Bean
    @ConditionalOnProperty(
            name = {"PHONE_AUTH_ENABLED", "PHONE_AUTH_SEND_ENABLED"},
            havingValue = "true")
    PhoneCaptchaVerifier phoneCaptchaVerifier(CoreSettings settings) throws Exception {
        com.aliyun.teaopenapi.models.Config config = aliyunConfig(
                settings, "captcha.cn-shanghai.aliyuncs.com");
        return new AliyunPhoneCaptchaVerifier(
                new com.aliyun.captcha20230305.Client(config),
                settings.aliyunCaptchaSceneId());
    }

    @Bean
    @ConditionalOnProperty(
            name = {"PHONE_AUTH_ENABLED", "PHONE_AUTH_SEND_ENABLED"},
            havingValue = "true")
    PhoneAuthService phoneAuthService(
            PhoneCaptchaVerifier captcha,
            PhoneSmsProvider sms,
            PhoneAuthRateLimiter rateLimiter,
            PhoneIdentityDigester digester,
            PhoneChallengeStore challenges,
            PhoneAuthRepository accounts,
            CoreSettings settings) {
        return new PhoneAuthService(
                captcha,
                sms,
                rateLimiter,
                digester,
                challenges,
                accounts,
                new SecurePhoneChallengeIdGenerator(),
                settings.phoneAuthConsentVersion());
    }

    private static com.aliyun.teaopenapi.models.Config aliyunConfig(
            CoreSettings settings, String endpoint) {
        return new com.aliyun.teaopenapi.models.Config()
                .setAccessKeyId(settings.aliyunAccessKeyId().reveal())
                .setAccessKeySecret(settings.aliyunAccessKeySecret().reveal())
                .setEndpoint(endpoint)
                .setProtocol("https")
                .setConnectTimeout(2_000)
                .setReadTimeout(4_000)
                .setMaxIdleConns(20)
                .setUserAgent("inkforge-phone-auth/1");
    }
}
