package cn.inkforge.core.outlines.domain;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.http.ApiException;
import java.util.List;
import org.junit.jupiter.api.Test;

class OutlineNodeValidatorTest {

    @Test
    void 接受三层树并拒绝闭区间重叠与父节点收缩() {
        var stage = node("stage", "stage", null, 1, 20);
        var first = node("a", "plot_unit", "stage", 2, 5);
        var second = node("b", "plot_unit", "stage", 6, 10);
        var existing = List.of(stage, first, second);

        OutlineNodeValidator.validate(
                node("group", "chapter_group", "a", 3, 4), existing, "章节组");
        assertCode(
                () -> OutlineNodeValidator.validate(
                        node("new", "plot_unit", "stage", 5, 6), existing, "重叠"),
                "OUTLINE_RANGE_OVERLAP");
        assertCode(
                () -> OutlineNodeValidator.validate(
                        node("stage", "stage", null, 1, 4), existing, "收缩"),
                "OUTLINE_CHILD_RANGE_OUTSIDE_PARENT");
    }

    @Test
    void 拒绝空标题缺失父节点和不完整范围() {
        assertCode(
                () -> OutlineNodeValidator.validate(
                        node("x", "stage", null, null, null), List.of(), " \n "),
                "OUTLINE_TITLE_REQUIRED");
        assertCode(
                () -> OutlineNodeValidator.validate(
                        node("x", "plot_unit", null, 1, 2), List.of(), "标题"),
                "OUTLINE_PARENT_REQUIRED");
        assertCode(
                () -> OutlineNodeValidator.validate(
                        node("x", "stage", null, 1, null), List.of(), "标题"),
                "OUTLINE_RANGE_PAIR_REQUIRED");
    }

    private static OutlineNodeSnapshot node(
            String id, String kind, String parent, Integer start, Integer end) {
        return new OutlineNodeSnapshot(id, kind, parent, start, end);
    }

    private static void assertCode(Runnable action, String code) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(ApiException.class, error ->
                        org.assertj.core.api.Assertions.assertThat(error.code())
                                .isEqualTo(code));
    }
}
