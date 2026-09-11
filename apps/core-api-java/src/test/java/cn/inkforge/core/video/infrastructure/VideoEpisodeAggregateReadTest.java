package cn.inkforge.core.video.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.http.ApiException;

import org.junit.jupiter.api.Test;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;

class VideoEpisodeAggregateReadTest {
    @Test
    void 首轮变化时用新正式head完整重组一次() {
        var assembled = new ArrayList<Integer>();
        var refreshed = new ArrayDeque<>(List.of(new Snapshot(2), new Snapshot(2)));

        int result =
                VideoEpisodeAggregateRead.read(
                        new Snapshot(1),
                        snapshot -> {
                            assembled.add(snapshot.revision());
                            return snapshot.revision();
                        },
                        refreshed::removeFirst,
                        Snapshot::revision);

        assertThat(result).isEqualTo(2);
        assertThat(assembled).containsExactly(1, 2);
        assertThat(refreshed).isEmpty();
    }

    @Test
    void 两轮正式head都变化时返回稳定冲突() {
        var assembled = new ArrayList<Integer>();
        var refreshed = new ArrayDeque<>(List.of(new Snapshot(2), new Snapshot(3)));

        assertThatThrownBy(
                        () ->
                                VideoEpisodeAggregateRead.read(
                                        new Snapshot(1),
                                        snapshot -> {
                                            assembled.add(snapshot.revision());
                                            return snapshot.revision();
                                        },
                                        refreshed::removeFirst,
                                        Snapshot::revision))
                .isInstanceOfSatisfying(
                        ApiException.class,
                        error -> {
                            assertThat(error.statusCode()).isEqualTo(409);
                            assertThat(error.code()).isEqualTo("VIDEO_EPISODE_SNAPSHOT_CHANGED");
                        });
        assertThat(assembled).containsExactly(1, 2);
        assertThat(refreshed).isEmpty();
    }

    private record Snapshot(int revision) {}
}
