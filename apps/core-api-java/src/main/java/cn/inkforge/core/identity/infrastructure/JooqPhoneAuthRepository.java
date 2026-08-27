package cn.inkforge.core.identity.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CREDITLEDGER;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.USERPHONEIDENTITY;

import cn.inkforge.core.identity.application.PhoneAccountResult;
import cn.inkforge.core.identity.application.PhoneAuthRepository;
import cn.inkforge.core.identity.domain.AuthUser;
import cn.inkforge.core.identity.domain.PasswordCodec;
import cn.inkforge.core.identity.domain.PhoneNumber;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.Base64;
import java.util.Objects;
import java.util.function.Supplier;
import org.jooq.DSLContext;
import org.jooq.exception.DataAccessException;
import org.postgresql.util.PSQLException;

/** 手机号身份仓储；新用户、手机号身份和唯一注册奖励在同一 PostgreSQL 事务内提交。 */
public final class JooqPhoneAuthRepository implements PhoneAuthRepository {

    private static final String PHONE_CONSTRAINT = "UserPhoneIdentity_phoneE164_key";

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final PasswordCodec passwords;
    private final Supplier<String> internalSecrets;

    public JooqPhoneAuthRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            PasswordCodec passwords) {
        this(database, ids, clock, passwords, secureSecretSupplier());
    }

    JooqPhoneAuthRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            PasswordCodec passwords,
            Supplier<String> internalSecrets) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.passwords = Objects.requireNonNull(passwords);
        this.internalSecrets = Objects.requireNonNull(internalSecrets);
    }

    @Override
    public PhoneAccountResult loginOrCreate(
            String phoneE164, String consentVersion, String verificationReference) {
        requireE164(phoneE164);
        requireNonBlank(consentVersion, "协议版本不能为空");
        requireNonBlank(verificationReference, "验证引用不能为空");
        try {
            return database.transactionResult(transaction -> {
                LocalDateTime now = now();
                AuthUser existing = findByPhone(transaction, phoneE164);
                if (existing != null) {
                    transaction.update(USERPHONEIDENTITY)
                            .set(USERPHONEIDENTITY.VERIFIEDAT, now)
                            .set(USERPHONEIDENTITY.UPDATEDAT, now)
                            .where(USERPHONEIDENTITY.PHONEE164.eq(phoneE164))
                            .execute();
                    return new PhoneAccountResult(existing, false);
                }

                String userId = ids.next();
                String internalUsername = "mobile_" + userId;
                String passwordHash = passwords.hash(requireNonBlank(
                        internalSecrets.get(), "内部账号密钥不能为空"));
                transaction.insertInto(USER)
                        .set(USER.ID, userId)
                        .set(USER.USERNAME, internalUsername)
                        .set(USER.PASSWORDHASH, passwordHash)
                        .set(USER.CREATEDAT, now)
                        .set(USER.UPDATEDAT, now)
                        .set(USER.CREDITBALANCEMICROS, JooqAuthRepository.SIGNUP_BONUS_MICROS)
                        .execute();
                transaction.insertInto(CREDITLEDGER)
                        .set(CREDITLEDGER.ID, ids.next())
                        .set(CREDITLEDGER.USERID, userId)
                        .set(CREDITLEDGER.TYPE, "signup_bonus")
                        .set(CREDITLEDGER.AMOUNTMICROS, JooqAuthRepository.SIGNUP_BONUS_MICROS)
                        .set(CREDITLEDGER.BALANCEAFTERMICROS, JooqAuthRepository.SIGNUP_BONUS_MICROS)
                        .set(CREDITLEDGER.PROMPTTOKENS, 0)
                        .set(CREDITLEDGER.COMPLETIONTOKENS, 0)
                        .set(CREDITLEDGER.CACHEDTOKENS, 0)
                        .set(CREDITLEDGER.TOTALTOKENS, 0)
                        .set(CREDITLEDGER.NOTE, "注册赠送 1000 积分")
                        .set(CREDITLEDGER.CREATEDAT, now)
                        .execute();
                transaction.insertInto(USERPHONEIDENTITY)
                        .set(USERPHONEIDENTITY.ID, ids.next())
                        .set(USERPHONEIDENTITY.USERID, userId)
                        .set(USERPHONEIDENTITY.PHONEE164, phoneE164)
                        .set(USERPHONEIDENTITY.VERIFIEDAT, now)
                        .set(USERPHONEIDENTITY.CONSENTVERSION, consentVersion)
                        .set(USERPHONEIDENTITY.CONSENTEDAT, now)
                        .set(USERPHONEIDENTITY.CREATEDAT, now)
                        .set(USERPHONEIDENTITY.UPDATEDAT, now)
                        .execute();
                return new PhoneAccountResult(
                        new AuthUser(
                                userId,
                                internalUsername,
                                passwordHash,
                                JooqAuthRepository.SIGNUP_BONUS_MICROS,
                                mask(phoneE164)),
                        true);
            });
        } catch (DataAccessException exception) {
            if (isPhoneConflict(exception)) {
                AuthUser winner = findByPhone(database.dsl(), phoneE164);
                if (winner != null) {
                    return new PhoneAccountResult(winner, false);
                }
            }
            throw exception;
        }
    }

    @Override
    public AuthUser findById(String userId) {
        return database.dsl()
                .select(
                        USER.ID,
                        USER.USERNAME,
                        USER.PASSWORDHASH,
                        USER.CREDITBALANCEMICROS,
                        USERPHONEIDENTITY.PHONEE164)
                .from(USER)
                .leftJoin(USERPHONEIDENTITY)
                .on(USERPHONEIDENTITY.USERID.eq(USER.ID))
                .where(USER.ID.eq(userId))
                .fetchOne(record -> map(
                        record.value1(),
                        record.value2(),
                        record.value3(),
                        record.value4(),
                        record.value5()));
    }

    private AuthUser findByPhone(DSLContext context, String phoneE164) {
        return context.select(
                        USER.ID,
                        USER.USERNAME,
                        USER.PASSWORDHASH,
                        USER.CREDITBALANCEMICROS)
                .from(USERPHONEIDENTITY)
                .join(USER)
                .on(USER.ID.eq(USERPHONEIDENTITY.USERID))
                .where(USERPHONEIDENTITY.PHONEE164.eq(phoneE164))
                .fetchOne(record -> map(
                        record.value1(),
                        record.value2(),
                        record.value3(),
                        record.value4(),
                        phoneE164));
    }

    private LocalDateTime now() {
        return LocalDateTime.ofInstant(
                clock.instant().truncatedTo(ChronoUnit.MILLIS), ZoneOffset.UTC);
    }

    private static AuthUser map(
            String id,
            String username,
            String passwordHash,
            Long creditBalanceMicros,
            String phoneE164) {
        return new AuthUser(
                id, username, passwordHash, creditBalanceMicros, mask(phoneE164));
    }

    private static String mask(String phoneE164) {
        if (phoneE164 == null) return null;
        return PhoneNumber.mainland(phoneE164.substring(3)).masked();
    }

    private static Supplier<String> secureSecretSupplier() {
        SecureRandom random = new SecureRandom();
        return () -> {
            byte[] value = new byte[32];
            random.nextBytes(value);
            return Base64.getUrlEncoder().withoutPadding().encodeToString(value);
        };
    }

    private static boolean isPhoneConflict(Throwable error) {
        Throwable current = error;
        for (int depth = 0; current != null && depth < 16; depth++) {
            if (current instanceof PSQLException postgres
                    && postgres.getServerErrorMessage() != null
                    && "23505".equals(postgres.getSQLState())
                    && PHONE_CONSTRAINT.equals(
                            postgres.getServerErrorMessage().getConstraint())) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }

    private static void requireE164(String value) {
        if (value == null || !value.matches("^\\+861[3-9][0-9]{9}$")) {
            throw new IllegalArgumentException("手机号格式无效");
        }
    }

    private static String requireNonBlank(String value, String message) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(message);
        }
        return value;
    }
}
