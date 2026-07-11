from __future__ import annotations


def extract_artifact_content(visible_content: str) -> str:
    start_marker = "ARTIFACT_OUTPUT_START"
    end_marker = "ARTIFACT_OUTPUT_END"
    if visible_content.count(start_marker) != 1 or visible_content.count(end_marker) != 1:
        raise ValueError("长文本草案必须包含唯一的开始和结束标记")
    _, remainder = visible_content.split(start_marker, 1)
    content, _ = remainder.split(end_marker, 1)
    return content.strip("\r\n")
