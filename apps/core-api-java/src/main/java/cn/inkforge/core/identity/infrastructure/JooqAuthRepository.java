package cn.inkforge.core.identity.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CREDITLEDGER;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.USERPHONEIDENTITY;

import cn.inkforge.core.db.generated.tables.records.UserRecord;
import cn.inkforge.core.identity.application.AuthRepository;
import cn.inkforge.core.identity.domain.AuthUser;
import cn.inkforge.core.identity.domain.DuplicateUsernameException;
import cn.inkforge.core.identity.domain.PhoneNumber;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import java.time.Clock;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import org.jooq.DSLContext;
import org.jooq.exception.DataAccessException;
import org.jooq.impl.DSL;
import org.postgresql.util.PSQLException;

/** jOOQ 认证仓储；用户与注册赠送流水始终在一个 PostgreSQL 事务内写入。 */
public final class JooqAuthRepository implements AuthRepository {

    public static final long SIGNUP_BONUS_MICROS = 1_000_000_000L;
    private static final String USERNAME_CONSTRAINT = "User_username_key";

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final boolean phoneIdentityAvailable;

    public JooqAuthRepository(CoreDatabase database, CuidV1Generator ids, Clock clock) {
        this(database, ids, clock, false);
    }

    public JooqAuthRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            boolean phoneIdentityAvailable) {
        this.database = java.util.Objects.requireNonNull(database);
        this.ids = java.util.Objects.requireNonNull(ids);
        this.clock = java.util.Objects.requireNonNull(clock);
        this.phoneIdentityAvailable = phoneIdentityAvailable;
    }

    @Override
    public AuthUser findByUsername(String username) {
        if (phoneIdentityAvailable) {
            return findWithPhone(USER.USERNAME.eq(username));
        }
        return map(database.dsl().selectFrom(USER)
                .where(USER.USERNAME.eq(username))
                .fetchOne());
    }

    @Override
    public AuthUser findById(String userId) {
        if (phoneIdentityAvailable) {
            return findWithPhone(USER.ID.eq(userId));
        }
        return map(database.dsl().selectFrom(USER)
                .where(USER.ID.eq(userId))
                .fetchOne());
    }

    @Override
    public AuthUser register(String username, String passwordHash) {
        try {
            return database.dsl().transactionResult(configuration -> {
                DSLContext transaction = DSL.using(configuration);
                LocalDateTime now = LocalDateTime.ofInstant(
                                clock.instant().truncatedTo(ChronoUnit.MILLIS), ZoneOffset.UTC);
                String userId = ids.next();
                transaction.insertInto(USER)
                        .set(USER.ID, userId)
                        .set(USER.USERNAME, username)
                        .set(USER.PASSWORDHASH, passwordHash)
                        .set(USER.CREATEDAT, now)
                        .set(USER.UPDATEDAT, now)
                        .set(USER.CREDITBALANCEMICROS, SIGNUP_BONUS_MICROS)
                        .execute();
                transaction.insertInto(CREDITLEDGER)
                        .set(CREDITLEDGER.ID, ids.next())
                        .set(CREDITLEDGER.USERID, userId)
                        .set(CREDITLEDGER.TYPE, "signup_bonus")
                        .set(CREDITLEDGER.AMOUNTMICROS, SIGNUP_BONUS_MICROS)
                        .set(CREDITLEDGER.BALANCEAFTERMICROS, SIGNUP_BONUS_MICROS)
                        .set(CREDITLEDGER.PROMPTTOKENS, 0)
                        .set(CREDITLEDGER.COMPLETIONTOKENS, 0)
                        .set(CREDITLEDGER.CACHEDTOKENS, 0)
                        .set(CREDITLEDGER.TOTALTOKENS, 0)
                        .set(CREDITLEDGER.NOTE, "注册赠送 1000 积分")
                        .set(CREDITLEDGER.CREATEDAT, now)
                        .execute();
                return new AuthUser(userId, username, passwordHash, SIGNUP_BONUS_MICROS);
            });
        } catch (DataAccessException exception) {
            if (isUsernameConflict(exception)) {
                throw new DuplicateUsernameException();
            }
            throw exception;
        }
    }

    private static AuthUser map(UserRecord user) {
        if (user == null) {
            return null;
        }
        return new AuthUser(
                user.getId(),
                user.getUsername(),
                user.getPasswordhash(),
                user.getCreditbalancemicros());
    }

    private AuthUser findWithPhone(org.jooq.Condition condition) {
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
                .where(condition)
                .fetchOne(record -> new AuthUser(
                        record.value1(),
                        record.value2(),
                        record.value3(),
                        record.value4(),
                        mask(record.value5())));
    }

    private static String mask(String phoneE164) {
        if (phoneE164 == null) return null;
        if (!phoneE164.matches("^\\+861[3-9][0-9]{9}$")) {
            throw new IllegalStateException("数据库手机号格式无效");
        }
        return PhoneNumber.mainland(phoneE164.substring(3)).masked();
    }

    private static boolean isUsernameConflict(Throwable error) {
        Throwable current = error;
        for (int depth = 0; current != null && depth < 16; depth++) {
            if (current instanceof PSQLException postgres
                    && postgres.getServerErrorMessage() != null
                    && "23505".equals(postgres.getSQLState())
                    && USERNAME_CONSTRAINT.equals(
                            postgres.getServerErrorMessage().getConstraint())) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }
}
