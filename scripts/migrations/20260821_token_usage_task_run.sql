BEGIN;

SET LOCAL search_path = public, pg_catalog;

-- 同一数据库内只允许一个执行者扩展并核验模型用量归集结构。
SELECT pg_advisory_xact_lock(hashtext('inkforge:20260821:TokenUsage:task-run'));

ALTER TABLE "TokenUsage" ADD COLUMN IF NOT EXISTS "requestId" TEXT;
ALTER TABLE "TokenUsage" ADD COLUMN IF NOT EXISTS "taskId" TEXT;
ALTER TABLE "TokenUsage" ADD COLUMN IF NOT EXISTS "runId" TEXT;

DO $migration$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'public."TokenUsage"'::regclass
      AND conname = 'TokenUsage_requestId_check'
  ) THEN
    ALTER TABLE "TokenUsage"
      ADD CONSTRAINT "TokenUsage_requestId_check"
      CHECK ("requestId" IS NULL OR btrim("requestId") <> '') NOT VALID;
  END IF;
END
$migration$;

ALTER TABLE "TokenUsage"
  VALIDATE CONSTRAINT "TokenUsage_requestId_check";

CREATE UNIQUE INDEX IF NOT EXISTS "TokenUsage_requestId_key"
ON "TokenUsage"("requestId");

CREATE INDEX IF NOT EXISTS "TokenUsage_userId_taskId_createdAt_idx"
ON "TokenUsage"("userId", "taskId", "createdAt");

CREATE INDEX IF NOT EXISTS "TokenUsage_runId_createdAt_idx"
ON "TokenUsage"("runId", "createdAt");

-- 重跑必须核验同名对象的实际定义，避免 IF NOT EXISTS 掩盖结构漂移。
DO $verification$
DECLARE
  relation_id OID := to_regclass('public."TokenUsage"');
  request_constraint TEXT;
  expected_index RECORD;
  index_matches BOOLEAN;
BEGIN
  IF relation_id IS NULL THEN
    RAISE EXCEPTION 'TokenUsage 迁移后仍不存在';
  END IF;

  IF (
    SELECT count(*)
    FROM pg_attribute AS attribute
    WHERE attribute.attrelid = relation_id
      AND attribute.attname IN ('requestId', 'taskId', 'runId')
      AND format_type(attribute.atttypid, attribute.atttypmod) = 'text'
      AND NOT attribute.attnotnull
      AND attribute.attnum > 0
      AND NOT attribute.attisdropped
  ) <> 3 THEN
    RAISE EXCEPTION 'TokenUsage 归集列类型或可空性不符合迁移契约';
  END IF;

  SELECT pg_get_constraintdef(constraint_definition.oid)
  INTO request_constraint
  FROM pg_constraint AS constraint_definition
  WHERE constraint_definition.conrelid = relation_id
    AND constraint_definition.conname = 'TokenUsage_requestId_check'
    AND constraint_definition.contype = 'c'
    AND constraint_definition.convalidated;

  IF request_constraint IS NULL
     OR position('btrim' IN request_constraint) = 0
     OR position('requestId' IN request_constraint) = 0
     OR position('IS NULL' IN request_constraint) = 0
     OR position('<> ' IN request_constraint) = 0 THEN
    RAISE EXCEPTION 'TokenUsage requestId 检查约束不符合迁移契约';
  END IF;

  FOR expected_index IN
    SELECT *
    FROM (
      VALUES
        ('TokenUsage_requestId_key', TRUE, 'requestId'),
        (
          'TokenUsage_userId_taskId_createdAt_idx',
          FALSE,
          'userId,taskId,createdAt'
        ),
        ('TokenUsage_runId_createdAt_idx', FALSE, 'runId,createdAt')
    ) AS definitions(name, is_unique, columns)
  LOOP
    SELECT EXISTS (
      SELECT 1
      FROM pg_index AS index_definition
      JOIN pg_class AS index_relation
        ON index_relation.oid = index_definition.indexrelid
      JOIN pg_am AS access_method
        ON access_method.oid = index_relation.relam
      WHERE index_definition.indrelid = relation_id
        AND index_relation.relname = expected_index.name
        AND access_method.amname = 'btree'
        AND index_definition.indisunique = expected_index.is_unique
        AND index_definition.indisvalid
        AND index_definition.indisready
        AND index_definition.indpred IS NULL
        AND index_definition.indexprs IS NULL
        AND index_definition.indnatts = index_definition.indnkeyatts
        AND NOT EXISTS (
          SELECT 1
          FROM unnest(index_definition.indoption) AS index_option(option_value)
          WHERE index_option.option_value <> 0
        )
        AND index_definition.indnkeyatts =
          array_length(string_to_array(expected_index.columns, ','), 1)
        AND (
          SELECT string_agg(attribute.attname, ',' ORDER BY index_key.ordinality)
          FROM unnest(index_definition.indkey) WITH ORDINALITY
            AS index_key(attribute_number, ordinality)
          JOIN pg_attribute AS attribute
            ON attribute.attrelid = index_definition.indrelid
            AND attribute.attnum = index_key.attribute_number
          WHERE index_key.ordinality <= index_definition.indnkeyatts
        ) = expected_index.columns
    ) INTO index_matches;

    IF NOT index_matches THEN
      RAISE EXCEPTION 'TokenUsage 归集索引定义不符合迁移契约：%',
        expected_index.name;
    END IF;
  END LOOP;
END
$verification$;

COMMIT;
