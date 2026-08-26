package cn.inkforge.core.writing.application;

import cn.inkforge.contracts.api.LongSerialStartWritingRunRequest;
import cn.inkforge.contracts.api.ShortMediumStartWritingRunRequest;
import cn.inkforge.contracts.api.StartWritingRunRequest;
import java.util.Objects;

/** 已按冻结联合契约完成严格校验的写作启动请求。 */
public sealed interface ParsedWritingRunStartRequest {

    record Legacy(StartWritingRunRequest request) implements ParsedWritingRunStartRequest {
        public Legacy {
            Objects.requireNonNull(request);
        }
    }

    record ShortMedium(ShortMediumStartWritingRunRequest request)
            implements ParsedWritingRunStartRequest {
        public ShortMedium {
            Objects.requireNonNull(request);
        }
    }

    record LongSerial(LongSerialStartWritingRunRequest request)
            implements ParsedWritingRunStartRequest {
        public LongSerial {
            Objects.requireNonNull(request);
        }
    }
}
