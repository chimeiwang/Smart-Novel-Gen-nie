package cn.inkforge.core.video.application;

/** 创建小说级视频项目时允许由浏览器决定的字段。 */
public record VideoProjectCreation(
        String title, String mode, String targetAspectRatio, String targetLanguage) {}
