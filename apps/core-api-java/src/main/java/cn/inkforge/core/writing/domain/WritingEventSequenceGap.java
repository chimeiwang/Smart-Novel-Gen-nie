package cn.inkforge.core.writing.domain;

/** Agent 事件序号不是下一条可接受序号，需要从耐久状态对账。 */
public final class WritingEventSequenceGap extends RuntimeException {

    private final int expectedSequence;
    private final int receivedSequence;

    public WritingEventSequenceGap(int expectedSequence, int receivedSequence) {
        super("智能体事件序号不连续，需要从稳定状态对账");
        this.expectedSequence = expectedSequence;
        this.receivedSequence = receivedSequence;
    }

    public int expectedSequence() {
        return expectedSequence;
    }

    public int receivedSequence() {
        return receivedSequence;
    }
}
