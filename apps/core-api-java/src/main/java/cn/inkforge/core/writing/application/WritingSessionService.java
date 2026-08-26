package cn.inkforge.core.writing.application;

import cn.inkforge.contracts.api.CreateMessageRequest;
import cn.inkforge.contracts.api.CreateWritingSessionRequest;
import cn.inkforge.contracts.api.MessageResponse;
import cn.inkforge.contracts.api.UpdateWritingSessionRequest;
import cn.inkforge.contracts.api.WritingSessionDetail;
import cn.inkforge.contracts.api.WritingSessionListItem;
import cn.inkforge.contracts.api.WritingSessionResponse;
import java.util.List;
import java.util.Objects;

/** 写作会话用例入口；HTTP 身份只能从 Cookie 当前用户传入。 */
public final class WritingSessionService {

    private final WritingSessionRepository repository;

    public WritingSessionService(WritingSessionRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public WritingSessionResponse create(
            String userId, CreateWritingSessionRequest request) {
        return repository.create(userId, request);
    }

    public List<WritingSessionListItem> list(
            String userId, String novelId, String chapterId) {
        return repository.list(userId, novelId, chapterId);
    }

    public WritingSessionDetail get(String userId, String sessionId) {
        return repository.get(userId, sessionId);
    }

    public WritingSessionResponse update(
            String userId, String sessionId, UpdateWritingSessionRequest request) {
        return repository.update(userId, sessionId, request);
    }

    public void delete(String userId, String sessionId) {
        repository.delete(userId, sessionId);
    }

    public MessageResponse addMessage(
            String userId, String sessionId, CreateMessageRequest request) {
        return repository.addMessage(userId, sessionId, request);
    }
}
