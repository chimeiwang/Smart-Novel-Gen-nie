package cn.inkforge.core.writing.application;

import cn.inkforge.contracts.api.CreateMessageRequest;
import cn.inkforge.contracts.api.CreateWritingSessionRequest;
import cn.inkforge.contracts.api.MessageResponse;
import cn.inkforge.contracts.api.UpdateWritingSessionRequest;
import cn.inkforge.contracts.api.WritingSessionDetail;
import cn.inkforge.contracts.api.WritingSessionListItem;
import cn.inkforge.contracts.api.WritingSessionResponse;
import java.util.List;

/** 作者写作会话与消息的权威持久化边界。 */
public interface WritingSessionRepository {

    WritingSessionResponse create(String userId, CreateWritingSessionRequest request);

    List<WritingSessionListItem> list(String userId, String novelId, String chapterId);

    WritingSessionDetail get(String userId, String sessionId);

    WritingSessionResponse update(
            String userId, String sessionId, UpdateWritingSessionRequest request);

    void delete(String userId, String sessionId);

    MessageResponse addMessage(
            String userId, String sessionId, CreateMessageRequest request);
}
