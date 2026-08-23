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
    expected_constraint record;
    actual_constraint_definition text;
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

    FOR expected_constraint IN
        SELECT *
        FROM (
            VALUES
                (
                    'TokenUsage_token_details_nonnegative_check',
                    $constraint$CHECK (((("promptCacheMissTokens" IS NULL) OR ("promptCacheMissTokens" >= 0)) AND (("reasoningTokens" IS NULL) OR ("reasoningTokens" >= 0))))$constraint$
                ),
                (
                    'TokenUsage_prompt_cache_details_check',
                    $constraint$CHECK (("promptCacheMissTokens" IS NULL) OR (("cachedTokens" + "promptCacheMissTokens") = "promptTokens"))$constraint$
                ),
                (
                    'TokenUsage_reasoning_details_check',
                    $constraint$CHECK (("reasoningTokens" IS NULL) OR ("reasoningTokens" <= "completionTokens"))$constraint$
                )
        ) AS definitions(name, definition)
    LOOP
        EXECUTE format(
            'ALTER TABLE "TokenUsage" VALIDATE CONSTRAINT %I',
            expected_constraint.name
        );

        SELECT regexp_replace(
            pg_get_constraintdef(constraint_definition.oid),
            '\s+',
            '',
            'g'
        )
        INTO actual_constraint_definition
        FROM pg_constraint AS constraint_definition
        WHERE constraint_definition.conrelid = table_oid
          AND constraint_definition.conname = expected_constraint.name
          AND constraint_definition.contype = 'c'
          AND constraint_definition.convalidated;

        IF actual_constraint_definition IS DISTINCT FROM regexp_replace(
            expected_constraint.definition,
            '\s+',
            '',
            'g'
        ) THEN
            RAISE EXCEPTION 'TokenUsage 检查约束定义不符合迁移契约：%',
                expected_constraint.name;
        END IF;
    END LOOP;
END;
$verification$;

COMMIT;
