package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.platform.http.ApiException;

import java.util.Objects;
import java.util.function.Function;
import java.util.function.Supplier;
import java.util.function.ToIntFunction;

/** 在 READ COMMITTED 下有限复核 Episode revision，保持正式 head 与其集合一致。草稿和候选仍以自身版本观察。 */
final class VideoEpisodeAggregateRead {
    private static final int MAX_ROUNDS = 2;

    private VideoEpisodeAggregateRead() {}

    static <S, T> T read(
            S initial,
            Function<S, T> assemble,
            Supplier<S> refresh,
            ToIntFunction<S> revision) {
        Objects.requireNonNull(assemble);
        Objects.requireNonNull(refresh);
        Objects.requireNonNull(revision);

        S snapshot = Objects.requireNonNull(initial);
        for (int round = 0; round < MAX_ROUNDS; round++) {
            int startingRevision = revision.applyAsInt(snapshot);
            T response = assemble.apply(snapshot);
            S current = Objects.requireNonNull(refresh.get());
            if (revision.applyAsInt(current) == startingRevision) return response;
            snapshot = current;
        }
        throw new ApiException(
                409,
                "VIDEO_EPISODE_SNAPSHOT_CHANGED",
                "分集正式版本在读取期间持续变化，请刷新后重试");
    }
}
