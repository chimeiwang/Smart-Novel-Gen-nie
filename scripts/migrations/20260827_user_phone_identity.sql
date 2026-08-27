BEGIN;

SET LOCAL search_path = public, pg_catalog;

-- 开发库可直接执行；正式库必须额外提供精确的自定义 GUC 确认令牌，其他数据库一律拒绝。
-- 生产调用示例：
-- PGOPTIONS='-c inkforge.user_phone_identity_production=novelwriter:20260827:apply' psql ... -f 本脚本
DO $safety$
DECLARE
  production_confirmation TEXT :=
    current_setting('inkforge.user_phone_identity_production', true);
BEGIN
  IF current_database() = 'novelwriterdev' THEN
    NULL;
  ELSIF current_database() = 'novelwriter'
      AND production_confirmation = 'novelwriter:20260827:apply' THEN
    NULL;
  ELSIF current_database() = 'novelwriter' THEN
    RAISE EXCEPTION '正式库手机号身份迁移缺少精确确认令牌';
  ELSE
    RAISE EXCEPTION
      '手机号身份迁移只允许在 novelwriterdev 或受确认的 novelwriter 执行，当前数据库为 %',
      current_database();
  END IF;
END
$safety$;

SELECT pg_advisory_xact_lock(hashtext('inkforge:20260827:user-phone-identity'));

CREATE TABLE IF NOT EXISTS "UserPhoneIdentity" (
  "id" TEXT NOT NULL,
  "userId" TEXT NOT NULL,
  "phoneE164" TEXT NOT NULL,
  "verifiedAt" TIMESTAMP(3) NOT NULL,
  "consentVersion" TEXT NOT NULL,
  "consentedAt" TIMESTAMP(3) NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "UserPhoneIdentity_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "UserPhoneIdentity_userId_key" UNIQUE ("userId"),
  CONSTRAINT "UserPhoneIdentity_phoneE164_key" UNIQUE ("phoneE164"),
  CONSTRAINT "UserPhoneIdentity_user_fkey"
    FOREIGN KEY ("userId") REFERENCES "User"("id")
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "UserPhoneIdentity_phone_check" CHECK (
    "phoneE164" ~ '^\+861[3-9][0-9]{9}$'
  ),
  CONSTRAINT "UserPhoneIdentity_consent_check" CHECK (
    btrim("consentVersion") <> '' AND length("consentVersion") <= 64
  ),
  CONSTRAINT "UserPhoneIdentity_time_check" CHECK (
    "verifiedAt" >= "createdAt"
    AND "consentedAt" >= "createdAt"
    AND "updatedAt" >= "createdAt"
  )
);

-- 迁移可能由 PostgreSQL 管理账户执行；新表必须继承现有 User 表的应用所有者约定。
DO $ownership$
DECLARE
  expected_owner OID;
  actual_owner OID;
  expected_owner_name TEXT;
BEGIN
  SELECT table_definition.relowner
  INTO expected_owner
  FROM pg_class AS table_definition
  JOIN pg_namespace AS namespace_definition
    ON namespace_definition.oid = table_definition.relnamespace
  WHERE namespace_definition.nspname = 'public'
    AND table_definition.relname = 'User'
    AND table_definition.relkind IN ('r', 'p');

  SELECT table_definition.relowner
  INTO actual_owner
  FROM pg_class AS table_definition
  JOIN pg_namespace AS namespace_definition
    ON namespace_definition.oid = table_definition.relnamespace
  WHERE namespace_definition.nspname = 'public'
    AND table_definition.relname = 'UserPhoneIdentity'
    AND table_definition.relkind IN ('r', 'p');

  IF expected_owner IS NULL OR actual_owner IS NULL THEN
    RAISE EXCEPTION 'User 或 UserPhoneIdentity 表所有者无法解析';
  END IF;

  IF actual_owner <> expected_owner THEN
    expected_owner_name := pg_get_userbyid(expected_owner);
    IF expected_owner_name IS NULL OR btrim(expected_owner_name) = '' THEN
      RAISE EXCEPTION 'User 表所有者角色无法解析';
    END IF;
    EXECUTE format(
      'ALTER TABLE public.%I OWNER TO %I',
      'UserPhoneIdentity',
      expected_owner_name
    );
  END IF;
END
$ownership$;

-- CREATE TABLE IF NOT EXISTS 不会校验同名旧表；显式核对关键约束，避免在畸形结构上静默成功。
DO $postcondition$
DECLARE
  missing_constraints TEXT[];
BEGIN
  SELECT array_agg(required.name ORDER BY required.name)
  INTO missing_constraints
  FROM (
    VALUES
      ('UserPhoneIdentity_pkey'),
      ('UserPhoneIdentity_userId_key'),
      ('UserPhoneIdentity_phoneE164_key'),
      ('UserPhoneIdentity_user_fkey'),
      ('UserPhoneIdentity_phone_check'),
      ('UserPhoneIdentity_consent_check'),
      ('UserPhoneIdentity_time_check')
  ) AS required(name)
  WHERE NOT EXISTS (
    SELECT 1
    FROM pg_constraint constraint_row
    WHERE constraint_row.conname = required.name
      AND constraint_row.conrelid = 'public."UserPhoneIdentity"'::regclass
  );

  IF missing_constraints IS NOT NULL THEN
    RAISE EXCEPTION 'UserPhoneIdentity 缺少预期约束：%', missing_constraints;
  END IF;

  IF (
    SELECT phone_table.relowner IS DISTINCT FROM user_table.relowner
    FROM pg_class AS phone_table
    JOIN pg_namespace AS phone_namespace ON phone_namespace.oid = phone_table.relnamespace
    CROSS JOIN pg_class AS user_table
    JOIN pg_namespace AS user_namespace ON user_namespace.oid = user_table.relnamespace
    WHERE phone_namespace.nspname = 'public'
      AND phone_table.relname = 'UserPhoneIdentity'
      AND phone_table.relkind IN ('r', 'p')
      AND user_namespace.nspname = 'public'
      AND user_table.relname = 'User'
      AND user_table.relkind IN ('r', 'p')
  ) IS DISTINCT FROM FALSE THEN
    RAISE EXCEPTION 'UserPhoneIdentity 与 User 表所有者不一致';
  END IF;
END
$postcondition$;

COMMIT;
