BEGIN;

SET LOCAL search_path = pg_catalog, public;
SELECT pg_advisory_xact_lock(hashtext('inkforge:20260823:token_usage_details'));

ALTER TABLE "TokenUsage"
    ADD COLUMN IF NOT EXISTS "promptCacheMissTokens" INTEGER;
ALTER TABLE "TokenUsage"
    ADD COLUMN IF NOT EXISTS "reasoningTokens" INTEGER;

DO $verification$
DECLARE
    table_oid oid;
    column_count integer;
    constraint_oid oid;
    constraint_definition text;
    constraint_validated boolean;
BEGIN
    SELECT c.oid
    INTO table_oid
    FROM pg_class AS c
    JOIN pg_namespace AS n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relname = 'TokenUsage'
      AND c.relkind IN ('r', 'p');

    IF table_oid IS NULL THEN
        RAISE EXCEPTION 'public."TokenUsage" 不存在';
    END IF;

    SELECT count(*)
    INTO column_count
    FROM pg_attribute AS attribute
    WHERE attribute.attrelid = table_oid
      AND attribute.attname IN ('promptCacheMissTokens', 'reasoningTokens')
      AND NOT attribute.attisdropped;

    IF column_count <> 2 THEN
        RAISE EXCEPTION 'TokenUsage Token 明细列数量不正确：%', column_count;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_attribute AS attribute
        WHERE attribute.attrelid = table_oid
          AND attribute.attname IN ('promptCacheMissTokens', 'reasoningTokens')
          AND NOT attribute.attisdropped
          AND (
              attribute.atttypid <> 'int4'::regtype
              OR attribute.attnotnull
              OR attribute.atthasdef
              OR attribute.attidentity <> ''
              OR attribute.attgenerated <> ''
          )
    ) THEN
        RAISE EXCEPTION 'TokenUsage Token 明细列必须是可空 INTEGER 且无生成定义';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = table_oid
          AND conname = 'TokenUsage_token_details_nonnegative_check'
    ) THEN
        EXECUTE 'ALTER TABLE "TokenUsage" ADD CONSTRAINT "TokenUsage_token_details_nonnegative_check" '
            || 'CHECK (("promptCacheMissTokens" IS NULL OR "promptCacheMissTokens" >= 0) '
            || 'AND ("reasoningTokens" IS NULL OR "reasoningTokens" >= 0)) NOT VALID';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = table_oid
          AND conname = 'TokenUsage_prompt_cache_details_check'
    ) THEN
        EXECUTE 'ALTER TABLE "TokenUsage" ADD CONSTRAINT "TokenUsage_prompt_cache_details_check" '
            || 'CHECK ("promptCacheMissTokens" IS NULL OR '
            || '"cachedTokens" + "promptCacheMissTokens" = "promptTokens") NOT VALID';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = table_oid
          AND conname = 'TokenUsage_reasoning_details_check'
    ) THEN
        EXECUTE 'ALTER TABLE "TokenUsage" ADD CONSTRAINT "TokenUsage_reasoning_details_check" '
            || 'CHECK ("reasoningTokens" IS NULL OR '
            || '"reasoningTokens" <= "completionTokens") NOT VALID';
    END IF;

    SELECT con.oid, pg_get_constraintdef(con.oid, true), con.convalidated
    INTO constraint_oid, constraint_definition, constraint_validated
    FROM pg_constraint AS con
    WHERE con.conrelid = table_oid
      AND con.conname = 'TokenUsage_token_details_nonnegative_check';
    IF constraint_oid IS NULL
       OR position('promptCacheMissTokens' IN constraint_definition) = 0
       OR position('reasoningTokens' IN constraint_definition) = 0
       OR position('>= 0' IN constraint_definition) = 0
       OR position('AND' IN upper(constraint_definition)) = 0 THEN
        RAISE EXCEPTION 'TokenUsage 非负约束定义不一致';
    END IF;
    IF NOT constraint_validated THEN
        EXECUTE 'ALTER TABLE "TokenUsage" VALIDATE CONSTRAINT "TokenUsage_token_details_nonnegative_check"';
    END IF;

    SELECT con.oid, pg_get_constraintdef(con.oid, true), con.convalidated
    INTO constraint_oid, constraint_definition, constraint_validated
    FROM pg_constraint AS con
    WHERE con.conrelid = table_oid
      AND con.conname = 'TokenUsage_prompt_cache_details_check';
    IF constraint_oid IS NULL
       OR position('cachedTokens' IN constraint_definition) = 0
       OR position('promptCacheMissTokens' IN constraint_definition) = 0
       OR position('promptTokens' IN constraint_definition) = 0
       OR position('+' IN constraint_definition) = 0
       OR position('=' IN constraint_definition) = 0 THEN
        RAISE EXCEPTION 'TokenUsage 缓存明细约束定义不一致';
    END IF;
    IF NOT constraint_validated THEN
        EXECUTE 'ALTER TABLE "TokenUsage" VALIDATE CONSTRAINT "TokenUsage_prompt_cache_details_check"';
    END IF;

    SELECT con.oid, pg_get_constraintdef(con.oid, true), con.convalidated
    INTO constraint_oid, constraint_definition, constraint_validated
    FROM pg_constraint AS con
    WHERE con.conrelid = table_oid
      AND con.conname = 'TokenUsage_reasoning_details_check';
    IF constraint_oid IS NULL
       OR position('reasoningTokens' IN constraint_definition) = 0
       OR position('completionTokens' IN constraint_definition) = 0
       OR position('<=' IN constraint_definition) = 0 THEN
        RAISE EXCEPTION 'TokenUsage 推理明细约束定义不一致';
    END IF;
    IF NOT constraint_validated THEN
        EXECUTE 'ALTER TABLE "TokenUsage" VALIDATE CONSTRAINT "TokenUsage_reasoning_details_check"';
    END IF;
END;
$verification$;

COMMIT;
