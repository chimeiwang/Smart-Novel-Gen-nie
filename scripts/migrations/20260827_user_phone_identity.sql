BEGIN;

SET LOCAL search_path = public, pg_catalog;

-- 本迁移目前只允许在隔离的 novelwriterdev 数据库验证；不得对 novelwriter 正式库执行。
DO $safety$
BEGIN
  IF current_database() <> 'novelwriterdev' THEN
    RAISE EXCEPTION '手机号身份迁移只允许在 novelwriterdev 执行，当前数据库为 %', current_database();
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
END
$postcondition$;

COMMIT;
