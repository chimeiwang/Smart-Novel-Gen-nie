-- 仅供空的 Compose 隔离验收库初始化：复现生产尚未开放的视频剧集列，不是生产回滚脚本。
DO $$
BEGIN
    IF current_database() <> 'novelwriterdev' OR current_user <> 'inkforge_e2e' THEN
        RAISE EXCEPTION '此夹具只允许用于指定的隔离测试数据库及账号';
    END IF;
END $$;

ALTER TABLE public."VideoEpisodeScriptVersion"
    DROP CONSTRAINT "VideoEpisodeScriptVersion_review_episode_fkey";
ALTER TABLE public."VideoStoryboardVersion"
    DROP CONSTRAINT "VideoStoryboardVersion_review_episode_fkey";
ALTER TABLE public."ReviewArtifact" DROP COLUMN "videoEpisodeId";
