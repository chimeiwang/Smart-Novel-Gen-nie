package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.video.application.VideoEpisodeTaskSubmitter;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import cn.inkforge.core.video.domain.VideoEpisodeScriptDocuments;
import cn.inkforge.core.video.domain.VideoEpisodeStoryboardDocuments;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Supplier;
import org.jooq.DSLContext;
import org.jooq.Record;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

/** 普通队列 Episode 业务任务；冻结来源和候选留在 Core，执行不创建模型 Step。 */
public final class VideoEpisodeTaskCoordinator implements cn.inkforge.core.video.application.VideoEpisodeTaskLifecycle {
    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final ObjectMapper json;
    private final CoreSettings settings;
    private final Supplier<VideoEpisodeTaskSubmitter> submitter;
    private final JooqVideoEpisodeRepository scripts;
    private final JooqVideoEpisodeStoryboardCandidateRepository storyboards;
    private volatile boolean stopped;

    VideoEpisodeTaskCoordinator(CoreDatabase database, CuidV1Generator ids, ObjectMapper json,
            CoreSettings settings, Supplier<VideoEpisodeTaskSubmitter> submitter,
            JooqVideoEpisodeRepository scripts, JooqVideoEpisodeStoryboardCandidateRepository storyboards) {
        this.database=database; this.ids=ids; this.json=json; this.settings=settings;
        this.submitter=submitter; this.scripts=scripts; this.storyboards=storyboards;
    }

    String create(DSLContext tx, String userId, String novelId, String episodeId,
            String requestId, String requestHash, String operation, String type,
            Map<String,Object> input, Map<String,Object> context, Integer draftRevision, OffsetDateTime draftTime) {
        String runId=ids.next(), bundleId=ids.next();
        // 业务记录使用实际来源中首个现存章作归属锚点，模型目标仍是完整 Episode。
        Record anchor=null;
        if ("video_episode_script".equals(type)) {
            List<?> sources=(List<?>)context.get("sources");
            for(Object source:sources) {
                String chapterId=(String)((Map<?,?>)source).get("chapterId");
                anchor=tx.fetchOne("SELECT id FROM public.\"Chapter\" WHERE id=? AND \"novelId\"=?",chapterId,novelId);
                if(anchor!=null) break;
            }
        } else {
            anchor=tx.fetchOne("""
                    SELECT c.id FROM public."VideoEpisodeScriptVersion" v
                    JOIN public."VideoEpisodeSourceSnapshot" s ON s."sourceSetVersionId"=v."sourceSetVersionId"
                    JOIN public."Chapter" c ON c.id=s."chapterId" AND c."novelId"=?
                    WHERE v.id=? AND v."episodeId"=? ORDER BY s.ordinal,s.id LIMIT 1
                    """,novelId,context.get("scriptVersionId"),episodeId);
        }
        if(anchor==null) throw invalid("视频来源缺少可验证的章节归属锚点");
        String chapterId=anchor.get("id",String.class);
        LocalDateTime now=LocalDateTime.now(java.time.Clock.systemUTC());
        Map<String,Object> body=new LinkedHashMap<>(input);
        body.put("dispatchNamespace",settings.videoDispatchNamespace());
        tx.execute("""
                INSERT INTO public."WorkflowRun" (id,"novelId","chapterId","userId",kind,status,input,
                  "sourceType","sourceId","createdAt","updatedAt","engineVersion",workflow,operation,
                  "idempotencyKey","requestHash","targetType","targetId",revision)
                VALUES (?,?,?,?,'chat','pending',?,?,?,?,?,1,'video',?,?,?,?,?,1)
                """,runId,novelId,chapterId,userId,json.writeValueAsString(body),type,episodeId,now,now,
                operation,requestId,requestHash,type,episodeId);
        String content=canonicalJson(context);
        String hash=ExecutionCanonicalJson.sha256(context);
        long bytes=content.getBytes(java.nio.charset.StandardCharsets.UTF_8).length;
        Map<String,Object> manifest=Map.of("schemaVersion",1,"taskId",runId,"resourceType",type+"_context",
                "resourceId",episodeId,"contentSha256",hash);
        tx.execute("""
                INSERT INTO public."WorkflowEvidenceBundle" (id,"runId",version,"policyVersion",
                  "manifestJson","manifestSha256","totalBytes","createdAt") VALUES (?,?,1,?,?,?,?,?)
                """,bundleId,runId,"video-episode-source/1.0",canonicalJson(manifest),
                ExecutionCanonicalJson.sha256(manifest),bytes,now);
        tx.execute("""
                INSERT INTO public."WorkflowEvidenceItem" (id,"bundleId",ordinal,"resourceType","resourceId",
                  exists,"resourceRevision","resourceUpdatedAt","contentType","contentJson","contentSha256",
                  "byteCount","metadataJson") VALUES (?,?,1,?,?,true,?,?,'json',?,?,?,?)
                """,ids.next(),bundleId,type+"_context",episodeId,draftRevision,
                draftTime==null?null:draftTime.withOffsetSameInstant(java.time.ZoneOffset.UTC).toLocalDateTime(),content,hash,bytes,"{}");
        tx.execute("UPDATE public.\"WorkflowRun\" SET \"currentEvidenceBundleId\"=? WHERE id=?",bundleId,runId);
        return runId;
    }

    /** 取消使用当前业务 revision 与稳定命令键，网络重放回读同一完整回执。 */
    public ObjectNode cancel(String userId,String episodeId,String taskId,String requestId,int revision) {
        return database.transactionResult(tx->{
            tx.fetchOne("SELECT pg_advisory_xact_lock(hashtextextended(?,0))","video-episode-command:"+userId+":"+requestId);
            String hash=ExecutionCanonicalJson.sha256(Map.of("taskId",taskId,"episodeId",episodeId,"revision",revision));
            Record prior=tx.fetchOne("SELECT * FROM public.\"VideoEpisodeCommand\" WHERE \"actorUserId\"=? AND \"clientRequestId\"=?",userId,requestId);
            if(prior!=null) {
                if(!hash.equals(prior.get("requestHash",String.class)) || !"episode.task.cancel".equals(prior.get("operation",String.class)))
                    throw new ApiException(409,"VIDEO_EPISODE_CLIENT_REQUEST_REUSED","请求标识已用于其他视频命令");
                return (ObjectNode)json.readTree(prior.get("resultJson",String.class));
            }
            Record episode=tx.fetchOne("""
                    SELECT e."projectId",e."novelId" FROM public."VideoEpisode" e
                    JOIN public."Novel" n ON n.id=e."novelId" AND n."userId"=?
                    WHERE e.id=? AND e."archivedAt" IS NULL
                    """,userId,episodeId);
            if(episode==null) throw new ApiException(404,"VIDEO_EPISODE_NOT_FOUND","分集不存在");
            Record run=owned(tx,userId,episode.get("novelId",String.class),taskId);
            if(!episodeId.equals(run.get("targetId",String.class))) throw invalid("任务不属于当前分集");
            if(!java.util.Objects.equals(revision,run.get("revision",Integer.class)))
                throw new ApiException(409,"VIDEO_EPISODE_TASK_REVISION_CONFLICT","任务版本已变化，请刷新");
            if(List.of("pending","running").contains(run.get("status",String.class))) {
                tx.execute("UPDATE public.\"WorkflowRun\" SET \"cancelRequestedAt\"=now(),\"cancelRequestId\"=?,\"updatedAt\"=now()-interval '31 seconds',revision=revision+1 WHERE id=?",requestId,taskId);
            }
            Record fresh=owned(tx,userId,episode.get("novelId",String.class),taskId);
            ObjectNode response=runResponse(tx,fresh);
            tx.execute("""
                    INSERT INTO public."VideoEpisodeCommand" (id,"actorUserId","clientRequestId","projectId",
                    "novelId","episodeId",operation,"requestHash","resultJson") VALUES (?,?,?,?,?,?,'episode.task.cancel',?,?)
                    """,ids.next(),userId,requestId,episode.get("projectId"),episode.get("novelId"),episodeId,hash,response.toString());
            return response;
        });
    }
    private ObjectNode runResponse(DSLContext tx,Record run) {
        ObjectNode result=json.createObjectNode();result.put("runId",run.get("id",String.class));
        result.put("episodeId",run.get("targetId",String.class));result.put("status",run.get("status",String.class));
        result.put("revision",run.get("revision",Integer.class));
        Record artifact=tx.fetchOne("SELECT id FROM public.\"ReviewArtifact\" WHERE \"workflowRunId\"=? ORDER BY \"createdAt\" DESC LIMIT 1",run.get("id"));
        result.set("artifactId",artifact==null?json.nullNode():json.valueToTree(artifact.get("id")));
        result.set("errorCode",json.valueToTree(run.get("errorCode")));result.set("errorMessage",json.valueToTree(run.get("errorMessage")));
        result.set("createdAt",json.valueToTree(cn.inkforge.core.platform.time.DatabaseTimestamp.api(run.get("createdAt",LocalDateTime.class))));
        result.set("updatedAt",json.valueToTree(cn.inkforge.core.platform.time.DatabaseTimestamp.api(run.get("updatedAt",LocalDateTime.class))));
        return result;
    }

    public ObjectNode progress(String userId,String novelId,String taskId) {
        return database.transactionResult(tx->{
            Record run=owned(tx,userId,novelId,taskId);
            ObjectNode body=(ObjectNode)json.readTree(run.get("input",String.class));
            ObjectNode result=json.createObjectNode();
            // 取消一经 Core 接受即停止新的模型阶段；数据库终态仍等网关取消收敛。
            result.put("status",run.get("cancelRequestedAt")!=null?"cancelled":run.get("status",String.class));
            result.set("checkpoint",body.has("checkpoint")?body.get("checkpoint"):json.nullNode());
            return result;
        });
    }

    /** 每次保存只推进业务检查点；结果仍在独立完成事务中接受来源和修订范围重验。 */
    public void checkpoint(String userId,String novelId,String taskId,JsonNode checkpoint) {
        if(checkpoint==null || !checkpoint.isObject()) throw invalid("检查点必须是完整对象");
        database.transactionResult(tx->{
            Record run=owned(tx,userId,novelId,taskId);
            if(run.get("cancelRequestedAt")!=null)
                throw new ApiException(409,"VIDEO_EPISODE_TASK_CANCELLED","视频任务已请求取消，不能开启或保存新的模型阶段");
            if (!List.of("pending","running").contains(run.get("status",String.class))) return null;
            ObjectNode input=(ObjectNode)json.readTree(run.get("input",String.class));
            JsonNode previous=input.path("checkpoint");
            if(previous.equals(checkpoint)) return null;
            requireCheckpointTransition(previous,checkpoint);
            input.set("checkpoint",checkpoint);
            tx.execute("UPDATE public.\"WorkflowRun\" SET input=?,status='running',revision=revision+1 WHERE id=?",
                    input.toString(),taskId);
            return null;
        });
    }

    private void requireCheckpointTransition(JsonNode previous,JsonNode next) {
        String oldPhase=previous.isObject()?previous.path("phase").asText():"generate";
        int oldCycle=previous.isObject()?previous.path("cycle").asInt(-1):0;
        String phase=next.path("phase").asText(); int cycle=next.path("cycle").asInt(-1);
        boolean valid=switch(oldPhase) {
            case "generate" -> "generate_started".equals(phase) && cycle==oldCycle;
            case "generate_started" -> "review".equals(phase) && cycle==oldCycle;
            case "review" -> "review_started".equals(phase) && cycle==oldCycle;
            case "review_started" -> ("complete".equals(phase) && cycle==oldCycle)
                    || ("generate".equals(phase) && oldCycle==0 && cycle==1);
            default -> false;
        };
        if(!valid || cycle<0 || cycle>1 || !next.has("candidate") || !next.has("review"))
            throw new ApiException(409,"VIDEO_EPISODE_CHECKPOINT_CONFLICT","检查点阶段不能回退或越过已开始的调用");
    }

    /** 重复回调只读终态；取消请求优先于迟到的成功，不触碰正式工作稿。 */
    public void complete(String userId,String novelId,String taskId,JsonNode result) {
        database.transactionResult(tx->{
            Record run=owned(tx,userId,novelId,taskId);
            if(!List.of("pending","running").contains(run.get("status",String.class))) return null;
            if(run.get("cancelRequestedAt")!=null) { finish(tx,taskId,"cancelled",null,null); return null; }
            try {
                tx.transactionResult(configuration -> {
                    DSLContext nested=org.jooq.impl.DSL.using(configuration);
                    Map<String,Object> context=context(nested,run);
                    requireCurrentSource(nested,run,context);
                    JsonNode saved=json.readTree(run.get("input",String.class)).path("checkpoint");
                    if(!"complete".equals(saved.path("phase").asText())
                            || !saved.path("candidate").equals(result.path("candidate"))
                            || !saved.path("review").equals(result.path("review")))
                        throw invalid("完成结果必须与完整已保存检查点一致");
                    Map<String,Object> proposal=map(result.path("candidate"));
                    Map<String,Object> review=map(result.path("review"));
                    requireReview(run.get("sourceType",String.class),review);
                    if("video_episode_script".equals(run.get("sourceType",String.class))) {
                        Map<String,Object> document=VideoEpisodeScriptDocuments.merge(context,proposal);
                        VideoEpisodeScriptDocuments.validateReview(document,review);
                        scripts.completeCandidate(nested,taskId,document,review);
                    } else {
                        Map<String,Object> document=VideoEpisodeStoryboardDocuments.merge(context,proposal);
                        VideoEpisodeStoryboardDocuments.validateReview(context,document,review);
                        storyboards.completeCandidate(nested,taskId,document,review);
                    }
                    return null;
                });
                finish(tx,taskId,"completed",null,null);
            } catch(ApiException error) {
                if(error.statusCode()>=500) throw error;
                finish(tx,taskId,"failed",error.code(),error.getMessage());
            } catch(IllegalArgumentException error) {
                finish(tx,taskId,"failed","VIDEO_EPISODE_OUTPUT_INVALID",error.getMessage());
            }
            return null;
        });
    }

    public void fail(String userId,String novelId,String taskId,String code,String message,boolean cancelled) {
        database.transactionResult(tx->{
            Record run=owned(tx,userId,novelId,taskId);
            if(List.of("pending","running").contains(run.get("status",String.class)))
                finish(tx,taskId,cancelled||run.get("cancelRequestedAt")!=null?"cancelled":"failed",code,message);
            return null;
        });
    }

    void requireReview(String sourceType,Map<String,Object> review) {
        boolean storyboard="video_episode_storyboard".equals(sourceType);
        int maxRequiredChanges=storyboard?30:20;
        int maxFindings=storyboard?200:100;
        if(!List.of("pass","revise").contains(review.get("decision"))
                || !(review.get("summary") instanceof String summary) || summary.isBlank()
                || !(review.get("requiredChanges") instanceof List<?> required)
                || !(review.get("findings") instanceof List<?> findings)
                || required.size()>maxRequiredChanges || findings.size()>maxFindings
                || ("revise".equals(review.get("decision")))!=!required.isEmpty())
            throw invalid("审阅结果缺少完整决定、修改项或问题依据");
    }

    private void requireCurrentSource(DSLContext tx,Record run,Map<String,Object> context) {
        String table="video_episode_script".equals(run.get("sourceType",String.class))
                ? "VideoEpisodeScriptDraft" : "VideoEpisodeStoryboardDraft";
        Record draft=tx.fetchOne("SELECT revision FROM public.\""+table+"\" WHERE \"episodeId\"=? FOR UPDATE",
                run.get("targetId",String.class));
        if(draft==null || !java.util.Objects.equals(((Number)context.get("draftRevision")).intValue(),draft.get("revision",Integer.class)))
            throw new ApiException(409,"VIDEO_EPISODE_SOURCE_CHANGED","工作稿已变化，不能接受旧任务候选");
    }

    public void run() throws InterruptedException {
        while(!stopped) {
            if(settings.videoPreviewEnabled() && settings.videoDispatchEnabled()
                    && settings.environment()!=CoreSettings.EnvironmentName.PRODUCTION) dispatchPending();
            Thread.sleep(1000);
        }
    }
    public void requestStop(){stopped=true;}

    private void dispatchPending() {
        String namespace=settings.videoDispatchNamespace();
        if(namespace==null || namespace.isBlank()) return;
        VideoEpisodeTaskSubmitter gateway=submitter.get(); if(gateway==null) return;
        List<Map<String,Object>> tasks=database.transactionResult(tx->{
            List<Map<String,Object>> ready=new java.util.ArrayList<>();
            for(Record run:tx.fetch("""
                    SELECT * FROM public."WorkflowRun" WHERE "engineVersion"=1 AND workflow='video'
                    AND "sourceType" IN ('video_episode_script','video_episode_storyboard')
                    AND status IN ('pending','running') AND (status='pending' OR "updatedAt" < now()-interval '30 seconds')
                    ORDER BY "createdAt" LIMIT 10 FOR UPDATE SKIP LOCKED
                    """)) {
                ObjectNode input=(ObjectNode)json.readTree(run.get("input",String.class));
                if(!namespace.equals(input.path("dispatchNamespace").asText())) continue;
                Map<String,Object> item=new LinkedHashMap<>();
                item.put("userId",run.get("userId")); item.put("novelId",run.get("novelId"));
                item.put("taskId",run.get("id"));item.put("cancelled",run.get("cancelRequestedAt")!=null);
                String operation=run.get("operation",String.class);
                String workflow=operation.replace("_generate","");
                item.put("payload",Map.of("workflow",workflow,"episodeId",run.get("targetId"),
                        "context",context(tx,run),"input",map(input)));
                tx.execute("UPDATE public.\"WorkflowRun\" SET status='running',\"updatedAt\"=now() WHERE id=?",run.get("id"));
                ready.add(item);
            }
            return ready;
        });
        for(Map<String,Object> task:tasks) {
            try {
                if(Boolean.TRUE.equals(task.get("cancelled"))) {
                    gateway.cancel((String)task.get("userId"),(String)task.get("novelId"),(String)task.get("taskId"));
                    fail((String)task.get("userId"),(String)task.get("novelId"),(String)task.get("taskId"),null,null,true);
                }
                else gateway.submit((String)task.get("userId"),(String)task.get("novelId"),(String)task.get("taskId"),cast(task.get("payload")));
            } catch(RuntimeException error) {
                // 受理结果未知时保留同一任务身份，下一轮重投，不伪造业务失败。
                org.slf4j.LoggerFactory.getLogger(getClass()).warn("视频任务投递失败 taskId={}",task.get("taskId"),error);
            }
        }
    }
    private Record owned(DSLContext tx,String userId,String novelId,String taskId) {
        Record run=tx.fetchOne("""
                SELECT r.* FROM public."WorkflowRun" r
                JOIN public."Novel" n ON n.id=r."novelId" AND n."userId"=r."userId"
                JOIN public."VideoEpisode" e ON e.id=r."targetId" AND e."novelId"=r."novelId"
                JOIN public."VideoProject" p ON p.id=e."projectId" AND p."novelId"=r."novelId"
                WHERE r.id=? AND r."userId"=? AND r."novelId"=?
                AND r."engineVersion"=1 AND r.workflow='video'
                AND r."sourceType" IN ('video_episode_script','video_episode_storyboard')
                AND r."sourceType"=r."targetType" AND r."sourceId"=r."targetId"
                AND r.operation IN ('episode_script_generate','episode_script_revise','episode_storyboard_generate','episode_storyboard_revise')
                FOR UPDATE OF r
                """,taskId,userId,novelId);
        if(run==null) throw new ApiException(404,"VIDEO_EPISODE_TASK_NOT_FOUND","视频任务不存在或归属不符");
        return run;
    }
    private Map<String,Object> context(DSLContext tx,Record run) {
        Record evidence=tx.fetchOne("SELECT \"contentJson\",\"contentSha256\" FROM public.\"WorkflowEvidenceItem\" WHERE \"bundleId\"=? AND \"resourceType\"=?",
                run.get("currentEvidenceBundleId"),run.get("sourceType",String.class)+"_context");
        if(evidence==null) throw invalid("视频任务缺少完整冻结来源");
        Map<String,Object> value=map(json.readTree(evidence.get("contentJson",String.class)));
        if(!ExecutionCanonicalJson.sha256(value).equals(evidence.get("contentSha256",String.class)))
            throw invalid("视频任务冻结来源哈希不一致");
        return value;
    }
    private Map<String,Object> map(JsonNode value) {
        if(!value.isObject()) throw invalid("视频任务结果必须是完整对象");
        return json.convertValue(value,new TypeReference<Map<String,Object>>(){});
    }
    @SuppressWarnings("unchecked") private static Map<String,Object> cast(Object value){return (Map<String,Object>)value;}
    private void finish(DSLContext tx,String id,String status,String code,String message) {
        tx.execute("UPDATE public.\"WorkflowRun\" SET status=CAST(? AS \"WorkflowRunStatus\"),\"errorCode\"=?,\"errorMessage\"=?,\"completedAt\"=now(),\"updatedAt\"=now(),revision=revision+1 WHERE id=?",status,code,message,id);
    }
    private static String canonicalJson(Object value){return new String(ExecutionCanonicalJson.bytes(value),java.nio.charset.StandardCharsets.UTF_8);}
    private static ApiException invalid(String message){return new ApiException(422,"VIDEO_EPISODE_TASK_INVALID",message);}
}
