package cn.inkforge.core.shortmedium.application;

import cn.inkforge.core.shortmedium.domain.ShortMediumDocument;
import cn.inkforge.core.shortmedium.domain.ShortMediumVersion;
import java.util.List;

/** 单个中短篇工作稿、版本、工作稿替换和采用回执的原子事务视图。 */
public interface ShortMediumVersionTransaction {

    ShortMediumDocument document();

    List<ShortMediumVersion> versions();

    ShortMediumVersion create(VersionCreation creation);

    ShortMediumVersion saveInitialDiff(ShortMediumVersion version, cn.inkforge.core.shortmedium.domain.DocumentDiff diff);

    void replaceWorkContent(String content);

    ShortMediumVersion markApplied(ShortMediumVersion candidate);

    String findAdoptionReplay(String key);

    void saveAdoptionReplay(String key, ShortMediumVersion candidate, String responseJson);

    ShortMediumVersion currentOutlineVersion();
}
