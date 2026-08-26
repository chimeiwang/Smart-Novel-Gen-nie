package cn.inkforge.core.novels.infrastructure;

import cn.inkforge.contracts.api.NovelResponse;
import cn.inkforge.contracts.api.AppliedStyleSummary;
import cn.inkforge.contracts.api.StoryLengthProfile;
import cn.inkforge.contracts.api.WorkspaceNovel;
import cn.inkforge.core.db.generated.enums.Storylengthprofile;
import cn.inkforge.core.db.generated.tables.records.NovelRecord;
import cn.inkforge.core.platform.time.DatabaseTimestamp;

/** 将冻结数据库记录映射为公共小说契约，集中处理枚举和 UTC 时间。 */
final class NovelReadMapper {

    NovelResponse novel(
            NovelRecord record,
            Storylengthprofile profile,
            Integer targetTotalWordCount) {
        NovelResponse response = new NovelResponse();
        response.setId(record.getId());
        response.setName(record.getName());
        response.setSummary(record.getSummary());
        response.setStoryProgress(record.getStoryprogress());
        response.setAppliedStyleId(record.getAppliedstyleid());
        response.setStoryLengthProfile(profile == null
                ? null
                : StoryLengthProfile.fromValue(profile.getLiteral()));
        response.setTargetTotalWordCount(targetTotalWordCount);
        response.setCreatedAt(DatabaseTimestamp.api(record.getCreatedat()));
        response.setUpdatedAt(DatabaseTimestamp.api(record.getUpdatedat()));
        return response;
    }

    WorkspaceNovel workspaceNovel(
            NovelRecord record,
            Storylengthprofile profile,
            Integer targetTotalWordCount,
            AppliedStyleSummary appliedStyle) {
        WorkspaceNovel response = new WorkspaceNovel();
        response.setId(record.getId());
        response.setName(record.getName());
        response.setSummary(record.getSummary());
        response.setStoryProgress(record.getStoryprogress());
        response.setAppliedStyleId(record.getAppliedstyleid());
        response.setAppliedStyle(appliedStyle);
        response.setStoryLengthProfile(profile == null
                ? null
                : StoryLengthProfile.fromValue(profile.getLiteral()));
        response.setTargetTotalWordCount(targetTotalWordCount);
        response.setCreatedAt(DatabaseTimestamp.api(record.getCreatedat()));
        response.setUpdatedAt(DatabaseTimestamp.api(record.getUpdatedat()));
        return response;
    }
}
