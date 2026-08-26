package cn.inkforge.core.writing.application;

import cn.inkforge.core.writing.domain.WritingAgentJobStatus;
import cn.inkforge.core.writing.domain.WritingDispatchRecord;

/** 把同一个耐久写作命令提交或取消到 Python Agent。 */
public interface WritingCommandSubmitter {

    WritingAgentJobStatus submit(WritingDispatchRecord command);

    void cancel(WritingDispatchRecord command);
}
