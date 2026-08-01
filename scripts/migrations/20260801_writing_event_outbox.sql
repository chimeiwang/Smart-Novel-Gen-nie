BEGIN;

SET LOCAL search_path = public, pg_catalog;

-- 同一数据库内只允许一个执行者创建并核验写作事件发件箱。
SELECT pg_advisory_xact_lock(hashtext('inkforge:20260801:WritingEventOutbox'));

DO $migration$
BEGIN
  IF to_regclass('public."WritingEventOutbox"') IS NULL THEN
    CREATE TABLE "WritingEventOutbox" (
      "id" TEXT NOT NULL,
      "taskId" TEXT NOT NULL,
      "commandId" TEXT,
      "sourceEventId" TEXT NOT NULL,
      "sourceSequence" INTEGER NOT NULL,
      "durableBaseline" INTEGER NOT NULL,
      "dedupeKey" TEXT NOT NULL,
      "eventType" TEXT NOT NULL,
      "payloadJson" TEXT NOT NULL,
      "deliveryState" TEXT NOT NULL DEFAULT 'pending'::text,
      "attemptCount" INTEGER NOT NULL DEFAULT 0,
      "nextAttemptAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
      "leaseToken" TEXT,
      "leaseExpiresAt" TIMESTAMP(3),
      "lastErrorCode" TEXT,
      "redisEventId" TEXT,
      "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
      "updatedAt" TIMESTAMP(3) NOT NULL,
      "publishedAt" TIMESTAMP(3),
      CONSTRAINT "WritingEventOutbox_pkey"
        PRIMARY KEY ("id"),
      CONSTRAINT "WritingEventOutbox_taskId_fkey"
        FOREIGN KEY ("taskId") REFERENCES "WritingTask"("id")
        ON DELETE CASCADE ON UPDATE CASCADE,
      CONSTRAINT "WritingEventOutbox_commandId_fkey"
        FOREIGN KEY ("commandId") REFERENCES "WritingRunCommand"("id")
        ON DELETE SET NULL ON UPDATE CASCADE,
      CONSTRAINT "WritingEventOutbox_sourceEventId_check"
        CHECK (btrim("sourceEventId") <> ''),
      CONSTRAINT "WritingEventOutbox_dedupeKey_check"
        CHECK (btrim("dedupeKey") <> ''),
      CONSTRAINT "WritingEventOutbox_sourceSequence_check"
        CHECK ("sourceSequence" > 0),
      CONSTRAINT "WritingEventOutbox_durableBaseline_check"
        CHECK (
          "durableBaseline" >= 0
          AND "durableBaseline" < "sourceSequence"
        ),
      CONSTRAINT "WritingEventOutbox_attemptCount_check"
        CHECK ("attemptCount" >= 0),
      CONSTRAINT "WritingEventOutbox_eventType_check"
        CHECK (
          "eventType" IN (
            'completed',
            'error',
            'artifact_awaiting_user_approval'
          )
        ),
      CONSTRAINT "WritingEventOutbox_deliveryState_check"
        CHECK (
          "deliveryState" IN (
            'pending',
            'delivering',
            'published',
            'blocked',
            'superseded'
          )
        ),
      CONSTRAINT "WritingEventOutbox_payloadJson_check"
        CHECK (COALESCE(jsonb_typeof("payloadJson"::jsonb) = 'object', FALSE)),
      CONSTRAINT "WritingEventOutbox_lease_check"
        CHECK (
          (
            "deliveryState" = 'delivering'
            AND "leaseToken" IS NOT NULL
            AND "leaseExpiresAt" IS NOT NULL
          )
          OR (
            "deliveryState" <> 'delivering'
            AND "leaseToken" IS NULL
            AND "leaseExpiresAt" IS NULL
          )
        ),
      CONSTRAINT "WritingEventOutbox_published_check"
        CHECK (
          (
            "deliveryState" = 'published'
            AND "redisEventId" IS NOT NULL
            AND "publishedAt" IS NOT NULL
          )
          OR (
            "deliveryState" <> 'published'
            AND "redisEventId" IS NULL
            AND "publishedAt" IS NULL
          )
        )
    );
  END IF;
END
$migration$;

CREATE UNIQUE INDEX IF NOT EXISTS "WritingEventOutbox_sourceEventId_key"
ON "WritingEventOutbox"("sourceEventId");

CREATE UNIQUE INDEX IF NOT EXISTS "WritingEventOutbox_dedupeKey_key"
ON "WritingEventOutbox"("dedupeKey");

CREATE UNIQUE INDEX IF NOT EXISTS "WritingEventOutbox_taskId_sourceSequence_key"
ON "WritingEventOutbox"("taskId", "sourceSequence");

CREATE INDEX IF NOT EXISTS "WritingEventOutbox_due_idx"
ON "WritingEventOutbox"("deliveryState", "nextAttemptAt", "createdAt")
WHERE "deliveryState" IN ('pending', 'delivering');

CREATE INDEX IF NOT EXISTS "WritingEventOutbox_task_sequence_idx"
ON "WritingEventOutbox"("taskId", "sourceSequence");

CREATE INDEX IF NOT EXISTS "WritingEventOutbox_publishedAt_idx"
ON "WritingEventOutbox"("publishedAt") WHERE "publishedAt" IS NOT NULL;

COMMENT ON TABLE "WritingEventOutbox" IS '写作边界事件事务发件箱';
COMMENT ON COLUMN "WritingEventOutbox"."taskId" IS '产生业务事实的写作任务';
COMMENT ON COLUMN "WritingEventOutbox"."commandId" IS '产生边界事实的运行命令，命令删除后保留事件';
COMMENT ON COLUMN "WritingEventOutbox"."sourceEventId" IS 'Agent 回调提供的稳定来源事件标识';
COMMENT ON COLUMN "WritingEventOutbox"."sourceSequence" IS '任务内严格递增的来源序号';
COMMENT ON COLUMN "WritingEventOutbox"."durableBaseline" IS '业务事务提交前已持久化的事件序号基线';
COMMENT ON COLUMN "WritingEventOutbox"."dedupeKey" IS '同一业务边界的唯一幂等键';
COMMENT ON COLUMN "WritingEventOutbox"."eventType" IS '允许通知的持久化业务边界类型';
COMMENT ON COLUMN "WritingEventOutbox"."payloadJson" IS 'Redis Stream 通知所需的最小 JSON 对象';
COMMENT ON COLUMN "WritingEventOutbox"."deliveryState" IS '通知投递状态，不代表业务执行结果';
COMMENT ON COLUMN "WritingEventOutbox"."attemptCount" IS '已获得投递租约的累计次数';
COMMENT ON COLUMN "WritingEventOutbox"."nextAttemptAt" IS 'pending 状态的下一次可领取时间';
COMMENT ON COLUMN "WritingEventOutbox"."leaseToken" IS '当前投递租约的所有权令牌';
COMMENT ON COLUMN "WritingEventOutbox"."leaseExpiresAt" IS '当前投递租约的到期时间';
COMMENT ON COLUMN "WritingEventOutbox"."lastErrorCode" IS '最近一次可诊断的稳定错误码';
COMMENT ON COLUMN "WritingEventOutbox"."redisEventId" IS '成功写入 Redis Stream 后返回的游标';
COMMENT ON COLUMN "WritingEventOutbox"."publishedAt" IS 'Redis Stream 已确认接收的时间';

-- 重跑只接受与本次迁移完全同名且核心定义一致的结构，避免 IF NOT EXISTS 掩盖漂移。
DO $verification$
DECLARE
  actual_columns TEXT[];
  actual_constraint_definition TEXT;
  expected_constraint RECORD;
  expected_index RECORD;
  index_matches BOOLEAN;
  relation_id OID := to_regclass('public."WritingEventOutbox"');
BEGIN
  IF relation_id IS NULL THEN
    RAISE EXCEPTION 'WritingEventOutbox 迁移后仍不存在';
  END IF;

  SELECT array_agg(attribute.attname::text ORDER BY attribute.attnum)
  INTO actual_columns
  FROM pg_attribute AS attribute
  WHERE attribute.attrelid = relation_id
    AND attribute.attnum > 0
    AND NOT attribute.attisdropped;

  IF actual_columns IS DISTINCT FROM ARRAY[
    'id',
    'taskId',
    'commandId',
    'sourceEventId',
    'sourceSequence',
    'durableBaseline',
    'dedupeKey',
    'eventType',
    'payloadJson',
    'deliveryState',
    'attemptCount',
    'nextAttemptAt',
    'leaseToken',
    'leaseExpiresAt',
    'lastErrorCode',
    'redisEventId',
    'createdAt',
    'updatedAt',
    'publishedAt'
  ]::text[] THEN
    RAISE EXCEPTION 'WritingEventOutbox 列集合或列顺序不符合迁移契约'
      USING DETAIL = array_to_string(actual_columns, ',');
  END IF;

  IF EXISTS (
    SELECT 1
    FROM (
      VALUES
        ('id', 'text', TRUE, ''),
        ('taskId', 'text', TRUE, ''),
        ('commandId', 'text', FALSE, ''),
        ('sourceEventId', 'text', TRUE, ''),
        ('sourceSequence', 'integer', TRUE, ''),
        ('durableBaseline', 'integer', TRUE, ''),
        ('dedupeKey', 'text', TRUE, ''),
        ('eventType', 'text', TRUE, ''),
        ('payloadJson', 'text', TRUE, ''),
        ('deliveryState', 'text', TRUE, '''pending''::text'),
        ('attemptCount', 'integer', TRUE, '0'),
        ('nextAttemptAt', 'timestamp(3) without time zone', TRUE, 'CURRENT_TIMESTAMP'),
        ('leaseToken', 'text', FALSE, ''),
        ('leaseExpiresAt', 'timestamp(3) without time zone', FALSE, ''),
        ('lastErrorCode', 'text', FALSE, ''),
        ('redisEventId', 'text', FALSE, ''),
        ('createdAt', 'timestamp(3) without time zone', TRUE, 'CURRENT_TIMESTAMP'),
        ('updatedAt', 'timestamp(3) without time zone', TRUE, ''),
        ('publishedAt', 'timestamp(3) without time zone', FALSE, '')
    ) AS expected(name, type_name, not_null, default_expression)
    LEFT JOIN pg_attribute AS attribute
      ON attribute.attrelid = relation_id
      AND attribute.attname = expected.name
      AND attribute.attnum > 0
      AND NOT attribute.attisdropped
    LEFT JOIN pg_attrdef AS default_value
      ON default_value.adrelid = relation_id
      AND default_value.adnum = attribute.attnum
    WHERE attribute.attname IS NULL
      OR format_type(attribute.atttypid, attribute.atttypmod) <> expected.type_name
      OR attribute.attnotnull <> expected.not_null
      OR COALESCE(pg_get_expr(default_value.adbin, default_value.adrelid), '')
        <> expected.default_expression
  ) THEN
    RAISE EXCEPTION 'WritingEventOutbox 列类型、可空性或默认值不符合迁移契约';
  END IF;

  IF (
    SELECT count(*)
    FROM pg_constraint
    WHERE conrelid = relation_id
  ) <> 13 OR EXISTS (
    SELECT required.name
    FROM (
      VALUES
        ('WritingEventOutbox_attemptCount_check'),
        ('WritingEventOutbox_commandId_fkey'),
        ('WritingEventOutbox_dedupeKey_check'),
        ('WritingEventOutbox_deliveryState_check'),
        ('WritingEventOutbox_durableBaseline_check'),
        ('WritingEventOutbox_eventType_check'),
        ('WritingEventOutbox_lease_check'),
        ('WritingEventOutbox_payloadJson_check'),
        ('WritingEventOutbox_pkey'),
        ('WritingEventOutbox_published_check'),
        ('WritingEventOutbox_sourceEventId_check'),
        ('WritingEventOutbox_sourceSequence_check'),
        ('WritingEventOutbox_taskId_fkey')
    ) AS required(name)
    WHERE NOT EXISTS (
      SELECT 1
      FROM pg_constraint AS constraint_definition
      WHERE constraint_definition.conrelid = relation_id
        AND constraint_definition.conname = required.name
        AND constraint_definition.convalidated
    )
  ) THEN
    RAISE EXCEPTION 'WritingEventOutbox 约束集合不符合迁移契约';
  END IF;

  FOR expected_constraint IN
    SELECT *
    FROM (
      VALUES
        (
          'WritingEventOutbox_attemptCount_check',
          $constraint$CHECK (("attemptCount" >= 0))$constraint$
        ),
        (
          'WritingEventOutbox_commandId_fkey',
          $constraint$FOREIGN KEY ("commandId") REFERENCES "WritingRunCommand"(id) ON UPDATE CASCADE ON DELETE SET NULL$constraint$
        ),
        (
          'WritingEventOutbox_dedupeKey_check',
          $constraint$CHECK ((btrim("dedupeKey") <> ''::text))$constraint$
        ),
        (
          'WritingEventOutbox_deliveryState_check',
          $constraint$CHECK (("deliveryState" = ANY (ARRAY['pending'::text, 'delivering'::text, 'published'::text, 'blocked'::text, 'superseded'::text])))$constraint$
        ),
        (
          'WritingEventOutbox_durableBaseline_check',
          $constraint$CHECK ((("durableBaseline" >= 0) AND ("durableBaseline" < "sourceSequence")))$constraint$
        ),
        (
          'WritingEventOutbox_eventType_check',
          $constraint$CHECK (("eventType" = ANY (ARRAY['completed'::text, 'error'::text, 'artifact_awaiting_user_approval'::text])))$constraint$
        ),
        (
          'WritingEventOutbox_lease_check',
          $constraint$CHECK (((("deliveryState" = 'delivering'::text) AND ("leaseToken" IS NOT NULL) AND ("leaseExpiresAt" IS NOT NULL)) OR (("deliveryState" <> 'delivering'::text) AND ("leaseToken" IS NULL) AND ("leaseExpiresAt" IS NULL))))$constraint$
        ),
        (
          'WritingEventOutbox_payloadJson_check',
          $constraint$CHECK (COALESCE((jsonb_typeof(("payloadJson")::jsonb) = 'object'::text), false))$constraint$
        ),
        (
          'WritingEventOutbox_pkey',
          $constraint$PRIMARY KEY (id)$constraint$
        ),
        (
          'WritingEventOutbox_published_check',
          $constraint$CHECK (((("deliveryState" = 'published'::text) AND ("redisEventId" IS NOT NULL) AND ("publishedAt" IS NOT NULL)) OR (("deliveryState" <> 'published'::text) AND ("redisEventId" IS NULL) AND ("publishedAt" IS NULL))))$constraint$
        ),
        (
          'WritingEventOutbox_sourceEventId_check',
          $constraint$CHECK ((btrim("sourceEventId") <> ''::text))$constraint$
        ),
        (
          'WritingEventOutbox_sourceSequence_check',
          $constraint$CHECK (("sourceSequence" > 0))$constraint$
        ),
        (
          'WritingEventOutbox_taskId_fkey',
          $constraint$FOREIGN KEY ("taskId") REFERENCES "WritingTask"(id) ON UPDATE CASCADE ON DELETE CASCADE$constraint$
        )
    ) AS definitions(name, definition)
  LOOP
    SELECT pg_get_constraintdef(constraint_definition.oid)
    INTO actual_constraint_definition
    FROM pg_constraint AS constraint_definition
    WHERE constraint_definition.conrelid = relation_id
      AND constraint_definition.conname = expected_constraint.name;

    IF actual_constraint_definition IS DISTINCT FROM expected_constraint.definition THEN
      RAISE EXCEPTION 'WritingEventOutbox 约束定义不符合迁移契约：%',
        expected_constraint.name;
    END IF;
  END LOOP;

  IF (
    SELECT count(*)
    FROM pg_index
    WHERE indrelid = relation_id
  ) <> 7 THEN
    RAISE EXCEPTION 'WritingEventOutbox 索引数量不符合迁移契约';
  END IF;

  FOR expected_index IN
    SELECT *
    FROM (
      VALUES
        ('WritingEventOutbox_pkey', TRUE, 'id', FALSE, NULL, NULL),
        ('WritingEventOutbox_sourceEventId_key', TRUE, 'sourceEventId', FALSE, NULL, NULL),
        ('WritingEventOutbox_dedupeKey_key', TRUE, 'dedupeKey', FALSE, NULL, NULL),
        (
          'WritingEventOutbox_taskId_sourceSequence_key',
          TRUE,
          'taskId,sourceSequence',
          FALSE,
          NULL,
          NULL
        ),
        (
          'WritingEventOutbox_due_idx',
          FALSE,
          'deliveryState,nextAttemptAt,createdAt',
          TRUE,
          'pending',
          'delivering'
        ),
        (
          'WritingEventOutbox_task_sequence_idx',
          FALSE,
          'taskId,sourceSequence',
          FALSE,
          NULL,
          NULL
        ),
        (
          'WritingEventOutbox_publishedAt_idx',
          FALSE,
          'publishedAt',
          TRUE,
          'publishedAt',
          'IS NOT NULL'
        )
    ) AS definitions(name, is_unique, columns, is_partial, predicate_token_one, predicate_token_two)
  LOOP
    SELECT EXISTS (
      SELECT 1
      FROM pg_index AS index_definition
      JOIN pg_class AS index_relation
        ON index_relation.oid = index_definition.indexrelid
      WHERE index_definition.indrelid = relation_id
        AND index_relation.relname = expected_index.name
        AND index_definition.indisunique = expected_index.is_unique
        AND index_definition.indisvalid
        AND index_definition.indisready
        AND (index_definition.indpred IS NOT NULL) = expected_index.is_partial
        AND (
          SELECT string_agg(attribute.attname, ',' ORDER BY index_key.ordinality)
          FROM unnest(index_definition.indkey) WITH ORDINALITY
            AS index_key(attribute_number, ordinality)
          JOIN pg_attribute AS attribute
            ON attribute.attrelid = index_definition.indrelid
            AND attribute.attnum = index_key.attribute_number
          WHERE index_key.ordinality <= index_definition.indnkeyatts
        ) = expected_index.columns
        AND (
          expected_index.predicate_token_one IS NULL
          OR position(
            expected_index.predicate_token_one
            IN pg_get_expr(index_definition.indpred, index_definition.indrelid)
          ) > 0
        )
        AND (
          expected_index.predicate_token_two IS NULL
          OR position(
            expected_index.predicate_token_two
            IN pg_get_expr(index_definition.indpred, index_definition.indrelid)
          ) > 0
        )
    ) INTO index_matches;

    IF NOT index_matches THEN
      RAISE EXCEPTION 'WritingEventOutbox 索引定义不符合迁移契约：%', expected_index.name;
    END IF;
  END LOOP;
END
$verification$;

COMMIT;
