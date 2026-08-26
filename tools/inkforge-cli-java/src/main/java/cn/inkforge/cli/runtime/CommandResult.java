package cn.inkforge.cli.runtime;

import tools.jackson.databind.JsonNode;

public sealed interface CommandResult permits CommandResult.JsonResult, CommandResult.JsonlResult {

    record JsonResult(JsonNode data) implements CommandResult {}

    record JsonlResult(JsonlProducer producer) implements CommandResult {}

    static JsonResult json(JsonNode data) {
        return new JsonResult(data);
    }

    static JsonlResult jsonl(JsonlProducer producer) {
        return new JsonlResult(producer);
    }

    @FunctionalInterface
    interface JsonlProducer {
        int produce(FrameEmitter emitter) throws Exception;
    }

    @FunctionalInterface
    interface FrameEmitter {
        void emit(JsonNode frame);
    }
}
