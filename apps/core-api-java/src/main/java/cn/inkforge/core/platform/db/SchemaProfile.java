package cn.inkforge.core.platform.db;

public enum SchemaProfile {
    FULL(true, true),
    WITHOUT_VIDEO_PREVIEW(false, true),
    WITHOUT_PHONE_AUTH(true, false),
    WITHOUT_VIDEO_PREVIEW_AND_PHONE_AUTH(false, false);

    private final boolean videoPreviewIncluded;
    private final boolean phoneAuthIncluded;

    SchemaProfile(boolean videoPreviewIncluded, boolean phoneAuthIncluded) {
        this.videoPreviewIncluded = videoPreviewIncluded;
        this.phoneAuthIncluded = phoneAuthIncluded;
    }

    static SchemaProfile forCapabilities(boolean videoPreviewEnabled, boolean phoneAuthEnabled) {
        if (videoPreviewEnabled && phoneAuthEnabled) {
            return FULL;
        }
        if (videoPreviewEnabled) {
            return WITHOUT_PHONE_AUTH;
        }
        if (phoneAuthEnabled) {
            return WITHOUT_VIDEO_PREVIEW;
        }
        return WITHOUT_VIDEO_PREVIEW_AND_PHONE_AUTH;
    }

    boolean includesVideoPreview() {
        return videoPreviewIncluded;
    }

    boolean includesPhoneAuth() {
        return phoneAuthIncluded;
    }
}
