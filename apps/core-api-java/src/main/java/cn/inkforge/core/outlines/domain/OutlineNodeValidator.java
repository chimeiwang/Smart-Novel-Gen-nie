package cn.inkforge.core.outlines.domain;

import cn.inkforge.core.platform.http.ApiException;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/** 验证 stage → plot_unit → chapter_group 三层树和同级闭区间。 */
public final class OutlineNodeValidator {

    private static final Map<String, String> PARENT_KIND = parentKinds();

    private OutlineNodeValidator() {}

    public static void validate(
            OutlineNodeSnapshot candidate,
            List<OutlineNodeSnapshot> existing,
            String title) {
        if (title.strip().isEmpty()) {
            throw invalid("OUTLINE_TITLE_REQUIRED", "大纲节点标题不能为空");
        }
        if (!PARENT_KIND.containsKey(candidate.kind())) {
            throw invalid("OUTLINE_KIND_INVALID", "大纲节点类型无效");
        }
        if ((candidate.start() == null) != (candidate.end() == null)) {
            throw invalid("OUTLINE_RANGE_PAIR_REQUIRED", "章节范围必须同时提供起止序号");
        }
        if (candidate.start() != null
                && (candidate.start() <= 0
                        || candidate.end() <= 0
                        || candidate.start() > candidate.end())) {
            throw invalid("OUTLINE_RANGE_INVALID", "章节范围必须为有效正整数闭区间");
        }

        Map<String, OutlineNodeSnapshot> byId = new HashMap<>();
        existing.stream()
                .filter(value -> !value.id().equals(candidate.id()))
                .forEach(value -> byId.put(value.id(), value));
        String requiredParentKind = PARENT_KIND.get(candidate.kind());
        if (requiredParentKind == null) {
            if (candidate.parentId() != null) {
                throw invalid("OUTLINE_PARENT_KIND_INVALID", "阶段节点必须位于顶层");
            }
        } else if (candidate.parentId() == null) {
            throw invalid("OUTLINE_PARENT_REQUIRED", "该大纲节点必须指定父节点");
        } else {
            OutlineNodeSnapshot parent = byId.get(candidate.parentId());
            if (parent == null) {
                throw invalid("OUTLINE_PARENT_NOT_FOUND", "父大纲节点不存在");
            }
            if (!requiredParentKind.equals(parent.kind())) {
                throw invalid("OUTLINE_PARENT_KIND_INVALID", "父子大纲节点类型不兼容");
            }
            if (!contains(parent, candidate)) {
                throw invalid("OUTLINE_RANGE_OUTSIDE_PARENT", "子节点章节范围必须位于父节点内");
            }
        }

        String expectedChildKind = PARENT_KIND.entrySet().stream()
                .filter(value -> candidate.kind().equals(value.getValue()))
                .map(Map.Entry::getKey)
                .findFirst()
                .orElse(null);
        List<OutlineNodeSnapshot> children = existing.stream()
                .filter(value -> candidate.id().equals(value.parentId()))
                .toList();
        if (children.stream().anyMatch(value -> !value.kind().equals(expectedChildKind))) {
            throw invalid("OUTLINE_CHILD_KIND_INVALID", "修改后子节点类型将与父节点不兼容");
        }
        if (children.stream().anyMatch(value -> !contains(candidate, value))) {
            throw invalid(
                    "OUTLINE_CHILD_RANGE_OUTSIDE_PARENT", "修改后的章节范围不能排除现有子节点");
        }
        for (OutlineNodeSnapshot sibling : existing) {
            if (sibling.id().equals(candidate.id())
                    || !java.util.Objects.equals(sibling.parentId(), candidate.parentId())) {
                continue;
            }
            if (overlaps(candidate, sibling)) {
                throw invalid("OUTLINE_RANGE_OVERLAP", "同级大纲节点章节范围不能重叠");
            }
        }
    }

    private static boolean contains(
            OutlineNodeSnapshot parent, OutlineNodeSnapshot child) {
        if (child.start() == null && child.end() == null) {
            return true;
        }
        if (parent.start() == null
                || parent.end() == null
                || child.start() == null
                || child.end() == null) {
            return false;
        }
        return parent.start() <= child.start() && child.end() <= parent.end();
    }

    private static boolean overlaps(
            OutlineNodeSnapshot left, OutlineNodeSnapshot right) {
        if (left.start() == null
                || left.end() == null
                || right.start() == null
                || right.end() == null) {
            return false;
        }
        return left.start() <= right.end() && right.start() <= left.end();
    }

    private static Map<String, String> parentKinds() {
        Map<String, String> result = new HashMap<>();
        result.put("stage", null);
        result.put("plot_unit", "stage");
        result.put("chapter_group", "plot_unit");
        return result;
    }

    private static ApiException invalid(String code, String message) {
        return new ApiException(422, code, message);
    }
}
