package cn.inkforge.core.writing.domain;

/** Agent 回调事务的耐久受理结果。 */
public record WritingCallbackAcceptance(
        boolean accepted,
        int persistedSequence,
        boolean alreadyApplied,
        String rejectionCode,
        String taskPhase,
        String commandStatus,
        String outboxEventId) {

    public static WritingCallbackAcceptance rejected(int sequence, String code) {
        return new WritingCallbackAcceptance(
                false, sequence, false, code, null, null, null);
    }
}
