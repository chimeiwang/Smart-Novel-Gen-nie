package cn.inkforge.core.novels.infrastructure;

import static cn.inkforge.core.db.generated.Tables.RAGDOCUMENT;
import static cn.inkforge.core.db.generated.Tables.REFERENCEMATERIAL;
import static cn.inkforge.core.db.generated.Tables.WRITINGSTYLE;

import cn.inkforge.contracts.api.AppliedStyleSummary;
import cn.inkforge.contracts.api.RagDocumentStatus;
import cn.inkforge.contracts.api.ReferenceDto;
import cn.inkforge.contracts.api.ReferenceType;
import cn.inkforge.contracts.api.StyleSourceType;
import cn.inkforge.contracts.api.StyleSummary;
import cn.inkforge.contracts.api.WorkspaceResourcesResponse;
import cn.inkforge.core.db.generated.enums.Ragdocumentstatus;
import cn.inkforge.core.db.generated.enums.Ragsourcetype;
import cn.inkforge.core.db.generated.tables.records.NovelRecord;
import cn.inkforge.core.db.generated.tables.records.RagdocumentRecord;
import cn.inkforge.core.db.generated.tables.records.ReferencematerialRecord;
import cn.inkforge.core.db.generated.tables.records.WritingstyleRecord;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.List;
import org.jooq.DSLContext;
import org.jooq.Record;

/** 参考资料与文风读取器；RAG 内部失败信息只投影为稳定公共文案。 */
final class WorkspaceResourcesReader {

    WorkspaceResourcesResponse read(
            DSLContext context, NovelRecord novel, String userId) {
        List<ReferenceDto> references = context.select(
                        REFERENCEMATERIAL.fields())
                .select(RAGDOCUMENT.fields())
                .from(REFERENCEMATERIAL)
                .leftJoin(RAGDOCUMENT)
                .on(RAGDOCUMENT.SOURCETYPE.eq(Ragsourcetype.reference_material)
                        .and(RAGDOCUMENT.SOURCEID.eq(REFERENCEMATERIAL.ID)))
                .where(REFERENCEMATERIAL.NOVELID.eq(novel.getId()))
                .orderBy(REFERENCEMATERIAL.UPDATEDAT.desc(), REFERENCEMATERIAL.ID.asc())
                .fetch(WorkspaceResourcesReader::reference);
        List<StyleSummary> styles = context.selectFrom(WRITINGSTYLE)
                .where(WRITINGSTYLE.USERID.eq(userId))
                .orderBy(WRITINGSTYLE.UPDATEDAT.desc(), WRITINGSTYLE.ID.asc())
                .fetch(WorkspaceResourcesReader::style);
        WorkspaceResourcesResponse result = new WorkspaceResourcesResponse();
        result.setReferences(references);
        result.setStyles(styles);
        result.setAppliedStyle(appliedStyle(context, novel, userId));
        return result;
    }

    AppliedStyleSummary appliedStyle(
            DSLContext context, NovelRecord novel, String userId) {
        if (novel.getAppliedstyleid() == null) return null;
        WritingstyleRecord style = context.selectFrom(WRITINGSTYLE)
                .where(WRITINGSTYLE.ID.eq(novel.getAppliedstyleid())
                        .and(WRITINGSTYLE.USERID.eq(userId)))
                .fetchOne();
        return style == null
                ? null
                : new AppliedStyleSummary(style.getId(), style.getName());
    }

    private static ReferenceDto reference(Record row) {
        ReferencematerialRecord value = row.into(REFERENCEMATERIAL);
        RagdocumentRecord document = row.get(RAGDOCUMENT.ID) == null
                ? null
                : row.into(RAGDOCUMENT);
        Ragdocumentstatus status = document == null
                ? Ragdocumentstatus.disabled
                : document.getStatus();
        return new ReferenceDto(
                value.getContent(),
                document == null ? sha256(value.getContent()) : document.getContenthash(),
                DatabaseTimestamp.api(value.getCreatedat()),
                document == null
                        ? null
                        : publicRagError(document.getStatus(), document.getErrormessage()),
                value.getId(),
                RagDocumentStatus.fromValue(status.getLiteral()),
                value.getSourceurl(),
                value.getTitle(),
                ReferenceType.fromValue(value.getType().getLiteral()),
                DatabaseTimestamp.api(value.getUpdatedat()));
    }

    private static StyleSummary style(WritingstyleRecord value) {
        StyleSummary result = new StyleSummary(
                value.getId(),
                value.getName(),
                StyleSourceType.fromValue(value.getSourcetype().getLiteral()));
        result.setPortraitMarkdown(value.getPortraitmarkdown());
        return result;
    }

    private static String publicRagError(
            Ragdocumentstatus status, String errorMessage) {
        if (status == Ragdocumentstatus.ready) return null;
        if (status == Ragdocumentstatus.failed) return "索引生成失败";
        if ("检索索引服务未配置".equals(errorMessage)
                || "等待重新索引".equals(errorMessage)) {
            return errorMessage;
        }
        return errorMessage == null ? null : "检索索引暂不可用";
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("JDK 缺少 SHA-256", error);
        }
    }
}
