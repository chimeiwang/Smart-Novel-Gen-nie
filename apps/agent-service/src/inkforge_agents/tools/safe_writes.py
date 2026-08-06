SAFE_STRUCTURED_WRITE_INSTRUCTION = (
    "安全写约束：实体、经历和参考资料的 create 必须提供本草案内稳定、"
    "重试或返工时保持不变的 16..256 字符 clientRequestId；update/delete 必须从"
    "只读资料中的权威上下文或对应详情读取 expectedUpdatedAt 并原样携带，不得臆造或刷新；"
    "无法取得权威版本时必须停止并说明，不能提交写入。"
)
