package cn.inkforge.core.shortmedium.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.DocumentType;
import cn.inkforge.contracts.api.ManualVersionRequest;
import cn.inkforge.contracts.api.VersionActionRequest;
import cn.inkforge.contracts.api.VersionPreviewRequest;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.shortmedium.domain.DocumentDiff;
import cn.inkforge.core.shortmedium.domain.DocumentDiffEngine;
import cn.inkforge.core.shortmedium.domain.ShortMediumDocument;
import cn.inkforge.core.shortmedium.domain.ShortMediumText;
import cn.inkforge.core.shortmedium.domain.ShortMediumVersion;
import cn.inkforge.core.shortmedium.domain.ShortMediumVersionPayload;
import cn.inkforge.core.shortmedium.domain.VersionDocumentBinding;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import org.junit.jupiter.api.Test;

class ShortMediumVersionServiceTest {

    private static final OffsetDateTime NOW = OffsetDateTime.parse("2026-07-30T00:00:00Z");

    @Test
    void 人工提交按请求标识幂等且相同正文不新增版本() {
        MemoryTransaction transaction = outline("初稿");
        ShortMediumVersionService service = service(transaction);
        var preview = service.preview(
                "user-1", "novel-1", new VersionPreviewRequest(DocumentType.OUTLINE));
        ManualVersionRequest request = manual(
                "request-12345678",
                null,
                transaction.document().updatedAt(),
                "初稿",
                preview.getConfirmationHash());

        var first = service.submitManual("user-1", "novel-1", request);
        var replay = service.submitManual("user-1", "novel-1", request);

        assertThat(replay.getId()).isEqualTo(first.getId());
        assertThat(transaction.versions()).hasSize(1);
        var noChangePreview = service.preview(
                "user-1",
                "novel-1",
                new VersionPreviewRequest(DocumentType.OUTLINE).baseVersionId(first.getId()));
        var noChange = service.submitManual(
                "user-1",
                "novel-1",
                manual(
                        "request-87654321",
                        first.getId(),
                        transaction.document().updatedAt(),
                        "初稿",
                        noChangePreview.getConfirmationHash()));
        assertThat(noChange.getId()).isEqualTo(first.getId());
        assertThat(transaction.versions()).hasSize(1);
    }

    @Test
    void 人工提交必须校验工作稿时间正文哈希与确认摘要() {
        MemoryTransaction transaction = outline("初稿");
        ShortMediumVersionService service = service(transaction);
        var preview = service.preview(
                "user-1", "novel-1", new VersionPreviewRequest(DocumentType.OUTLINE));

        assertCode(
                () -> service.submitManual(
                        "user-1",
                        "novel-1",
                        manual(
                                "request-12345678",
                                null,
                                NOW.plusSeconds(1),
                                "初稿",
                                preview.getConfirmationHash())),
                "SHORT_MEDIUM_WORK_DRAFT_CONFLICT");
        assertCode(
                () -> service.submitManual(
                        "user-1",
                        "novel-1",
                        manual(
                                "request-12345678",
                                null,
                                NOW,
                                "别的正文",
                                preview.getConfirmationHash())),
                "SHORT_MEDIUM_WORK_DRAFT_HASH_CONFLICT");
        assertCode(
                () -> service.submitManual(
                        "user-1",
                        "novel-1",
                        manual(
                                "request-12345678",
                                null,
                                NOW,
                                "初稿",
                                "0".repeat(64))),
                "SHORT_MEDIUM_CONFIRMATION_CONFLICT");
    }

    @Test
    void 候选采用要求干净工作稿并按命令回执只应用一次() {
        MemoryTransaction transaction = outline("初稿");
        ShortMediumVersion base = transaction.addAppliedManual("初稿", null, "request-base-0001");
        ShortMediumVersion candidate = transaction.addAgentCandidate(
                "候选大纲", base.id(), "task-1", "job-1");
        ShortMediumVersionService service = service(transaction);
        DocumentDiff confirmation = DocumentDiffEngine.bind(
                DocumentDiffEngine.build("初稿", "候选大纲", base.id(), candidate.id()),
                "outline",
                null,
                base.id(),
                ShortMediumText.sha256("初稿"),
                candidate.id());
        VersionActionRequest request = action(
                "request-adopt-123", base.id(), confirmation.confirmationHash());

        transaction.changeWorkDraft("未提交人工修改");
        assertCode(
                () -> service.adopt("user-1", "novel-1", candidate.id(), request),
                "SHORT_MEDIUM_WORK_DRAFT_DIRTY");

        transaction.changeWorkDraft("初稿");
        var adopted = service.adopt("user-1", "novel-1", candidate.id(), request);
        var replay = service.adopt("user-1", "novel-1", candidate.id(), request);
        assertThat(adopted.getStatus().getValue()).isEqualTo("applied");
        assertThat(replay.getId()).isEqualTo(adopted.getId());
        assertThat(transaction.document().content()).isEqualTo("候选大纲");
        assertThat(transaction.replaceCount).isEqualTo(1);
        assertThat(transaction.replaySaveCount).isEqualTo(1);
    }

    @Test
    void 过期候选拒绝且恢复创建单调新版本不覆盖历史() {
        MemoryTransaction transaction = outline("第一版");
        ShortMediumVersion first = transaction.addAppliedManual("第一版", null, "request-first-001");
        ShortMediumVersion stale = transaction.addAgentCandidate(
                "过时候选", first.id(), "task-stale", "job-stale");
        ShortMediumVersion second = transaction.addAppliedManual(
                "第二版", first.id(), "request-second-01");
        transaction.changeWorkDraft("第二版");
        ShortMediumVersionService service = service(transaction);

        assertCode(
                () -> service.adopt(
                        "user-1",
                        "novel-1",
                        stale.id(),
                        action("request-stale-001", second.id(), "0".repeat(64))),
                "SHORT_MEDIUM_CANDIDATE_STALE");

        var diff = service.diffVersions("user-1", "novel-1", second.id(), first.id());
        var restored = service.restore(
                "user-1",
                "novel-1",
                first.id(),
                action("request-restore-1", second.id(), diff.getConfirmationHash()));
        assertThat(restored.getVersionNumber()).isEqualTo(4);
        assertThat(restored.getRestoredFromVersionId()).isEqualTo(first.id());
        assertThat(transaction.document().content()).isEqualTo("第一版");
        assertThat(transaction.versions().getFirst().content()).isEqualTo("第一版");
    }

    private static ShortMediumVersionService service(MemoryTransaction transaction) {
        return new ShortMediumVersionService(new MemoryRepository(transaction));
    }

    private static MemoryTransaction outline(String content) {
        return new MemoryTransaction(new ShortMediumDocument(
                "novel-1",
                null,
                new VersionDocumentBinding("outline", null),
                "short-medium:outline:novel-1",
                content,
                NOW));
    }

    private static ManualVersionRequest manual(
            String requestId,
            String baseVersionId,
            OffsetDateTime updatedAt,
            String content,
            String confirmationHash) {
        return new ManualVersionRequest(
                        requestId,
                        confirmationHash,
                        ShortMediumText.sha256(content),
                        DocumentType.OUTLINE,
                        updatedAt)
                .baseVersionId(baseVersionId);
    }

    private static VersionActionRequest action(
            String requestId, String baseVersionId, String confirmationHash) {
        return new VersionActionRequest(requestId, confirmationHash, DocumentType.OUTLINE)
                .baseVersionId(baseVersionId);
    }

    private static void assertCode(Runnable action, String expected) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo(expected));
    }

    private static final class MemoryRepository implements ShortMediumVersionRepository {
        private final MemoryTransaction transaction;

        private MemoryRepository(MemoryTransaction transaction) {
            this.transaction = transaction;
        }

        @Override
        public <T> T inDocument(
                String userId,
                String novelId,
                VersionDocumentBinding binding,
                Function<ShortMediumVersionTransaction, T> operation) {
            assertThat(userId).isEqualTo("user-1");
            assertThat(novelId).isEqualTo("novel-1");
            assertThat(binding).isEqualTo(transaction.document().binding());
            return operation.apply(transaction);
        }

        @Override
        public List<ShortMediumVersion> list(
                String userId, String novelId, VersionDocumentBinding binding) {
            return List.copyOf(transaction.versions());
        }

        @Override
        public ShortMediumVersion requireVersion(
                String userId, String novelId, String versionId) {
            return transaction.versions().stream()
                    .filter(version -> version.id().equals(versionId))
                    .findFirst()
                    .orElseThrow(() -> new ApiException(
                            404, "SHORT_MEDIUM_VERSION_NOT_FOUND", "中短篇版本不存在"));
        }
    }

    private static final class MemoryTransaction implements ShortMediumVersionTransaction {
        private ShortMediumDocument document;
        private final List<ShortMediumVersion> versions = new ArrayList<>();
        private final Map<String, String> replays = new HashMap<>();
        private int replaceCount;
        private int replaySaveCount;

        private MemoryTransaction(ShortMediumDocument document) {
            this.document = document;
        }

        @Override
        public ShortMediumDocument document() {
            return document;
        }

        @Override
        public List<ShortMediumVersion> versions() {
            return versions;
        }

        @Override
        public ShortMediumVersion create(VersionCreation creation) {
            String id = "version-" + (versions.size() + 1);
            ShortMediumVersion created = new ShortMediumVersion(
                    id,
                    document.novelId(),
                    document.chapterId(),
                    document.artifactKey(),
                    creation.status(),
                    creation.summary(),
                    creation.payload(),
                    creation.diff().withToVersionId(id),
                    creation.createdByAgent(),
                    creation.taskId(),
                    NOW.plusSeconds(versions.size()),
                    NOW.plusSeconds(versions.size()),
                    "applied".equals(creation.status()) ? NOW : null);
            versions.add(created);
            return created;
        }

        @Override
        public ShortMediumVersion saveInitialDiff(
                ShortMediumVersion version, DocumentDiff diff) {
            ShortMediumVersion updated = version.withDiff(diff);
            versions.set(versions.indexOf(version), updated);
            return updated;
        }

        @Override
        public void replaceWorkContent(String content) {
            replaceCount++;
            document = document.withContent(content, document.updatedAt().plusNanos(1_000_000));
        }

        @Override
        public ShortMediumVersion markApplied(ShortMediumVersion candidate) {
            ShortMediumVersion applied = candidate.withStatus("applied", NOW, NOW);
            versions.set(versions.indexOf(candidate), applied);
            return applied;
        }

        @Override
        public String findAdoptionReplay(String key) {
            return replays.get(key);
        }

        @Override
        public void saveAdoptionReplay(
                String key, ShortMediumVersion candidate, String responseJson) {
            replaySaveCount++;
            replays.put(key, responseJson);
        }

        @Override
        public ShortMediumVersion currentOutlineVersion() {
            return current();
        }

        private ShortMediumVersion addAppliedManual(
                String content, String baseVersionId, String requestId) {
            ShortMediumVersionPayload payload = new ShortMediumVersionPayload(
                    "outline_draft",
                    "outline",
                    versions.size() + 1,
                    baseVersionId,
                    requestId,
                    "manual",
                    content,
                    ShortMediumText.sha256(content),
                    null,
                    null,
                    null,
                    null,
                    null,
                    null,
                    null,
                    false,
                    null,
                    null,
                    null);
            ShortMediumVersion created = create(new VersionCreation(
                    payload,
                    DocumentDiffEngine.build(
                            current() == null ? "" : current().content(),
                            content,
                            baseVersionId,
                            null),
                    "applied",
                    null,
                    null,
                    null,
                    null));
            changeWorkDraft(content);
            return created;
        }

        private ShortMediumVersion addAgentCandidate(
                String content, String baseVersionId, String taskId, String jobId) {
            ShortMediumVersionPayload payload = new ShortMediumVersionPayload(
                    "outline_draft",
                    "outline",
                    versions.size() + 1,
                    baseVersionId,
                    null,
                    "agent",
                    content,
                    ShortMediumText.sha256(content),
                    taskId,
                    jobId,
                    null,
                    null,
                    null,
                    null,
                    null,
                    false,
                    null,
                    null,
                    null);
            ShortMediumVersion created = create(new VersionCreation(
                    payload,
                    DocumentDiffEngine.build(
                            current() == null ? "" : current().content(),
                            content,
                            baseVersionId,
                            null),
                    "awaiting_user",
                    null,
                    "剧情",
                    taskId,
                    jobId));
            DocumentDiff bound = DocumentDiffEngine.bind(
                    created.diff(),
                    "outline",
                    null,
                    baseVersionId,
                    current() == null
                            ? ShortMediumText.sha256("")
                            : current().payload().contentHash(),
                    created.id());
            ShortMediumVersion updated = created.withDiff(bound);
            versions.set(versions.indexOf(created), updated);
            return updated;
        }

        private ShortMediumVersion current() {
            return versions.stream()
                    .filter(version -> "applied".equals(version.status()))
                    .max(java.util.Comparator.comparingInt(ShortMediumVersion::versionNumber))
                    .orElse(null);
        }

        private void changeWorkDraft(String content) {
            document = document.withContent(content, document.updatedAt());
        }
    }
}
