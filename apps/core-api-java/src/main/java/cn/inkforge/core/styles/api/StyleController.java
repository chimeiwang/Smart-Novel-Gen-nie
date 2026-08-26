package cn.inkforge.core.styles.api;

import cn.inkforge.contracts.api.ApplyStyleRequest;
import cn.inkforge.contracts.api.ApplyStyleResponse;
import cn.inkforge.contracts.api.Body1;
import cn.inkforge.contracts.api.CreateStyleRequest;
import cn.inkforge.contracts.api.FullPortraitSuccessRequest;
import cn.inkforge.contracts.api.PortraitAcceptedResponse;
import cn.inkforge.contracts.api.PortraitContextRequest;
import cn.inkforge.contracts.api.PortraitContextResponse;
import cn.inkforge.contracts.api.PortraitFailureRequest;
import cn.inkforge.contracts.api.PortraitProcessingRequest;
import cn.inkforge.contracts.api.PortraitTaskResponse;
import cn.inkforge.contracts.api.SectionPortraitSuccessRequest;
import cn.inkforge.contracts.api.StyleReferenceResponse;
import cn.inkforge.contracts.api.StyleResponse;
import cn.inkforge.contracts.api.UpdatePortraitSectionRequest;
import cn.inkforge.core.generated.api.StylesApi;
import cn.inkforge.core.identity.application.AuthenticatedUser;
import cn.inkforge.core.identity.application.CurrentUserAccess;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.http.InternalServiceAuthenticator;
import cn.inkforge.core.platform.http.RawRequestBody;
import cn.inkforge.core.styles.application.StyleService;
import cn.inkforge.core.styles.domain.PortraitSection;
import cn.inkforge.serviceauth.ServiceScope;
import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import java.util.Optional;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;
import org.springframework.web.multipart.MultipartFile;

/** 冻结的十个作者文风接口和四个受签名画像回调。 */
@RestController
public final class StyleController implements StylesApi {

    private final Optional<StyleService> configuredService;
    private final Optional<CurrentUserAccess> configuredUsers;
    private final Optional<InternalServiceAuthenticator> configuredAuthenticator;

    public StyleController(
            Optional<StyleService> configuredService,
            Optional<CurrentUserAccess> configuredUsers,
            Optional<InternalServiceAuthenticator> configuredAuthenticator) {
        this.configuredService = configuredService;
        this.configuredUsers = configuredUsers;
        this.configuredAuthenticator = configuredAuthenticator;
    }

    @Override
    public ResponseEntity<List<StyleResponse>> listStylesApiV1StylesGet(String token) {
        return ResponseEntity.ok(service().list(user(token).id()));
    }

    @Override
    public ResponseEntity<StyleResponse> createStyleApiV1StylesPost(
            CreateStyleRequest request, String token) {
        return ResponseEntity.status(201).body(service().create(user(token).id(), request));
    }

    @Override
    public ResponseEntity<Void> deleteStyleApiV1StylesStyleIdDelete(
            String styleId, String token) {
        service().deleteStyle(user(token).id(), styleId);
        return ResponseEntity.noContent().build();
    }

    @Override
    public ResponseEntity<StyleReferenceResponse>
            uploadReferenceApiV1StylesStyleIdReferencesPost(
                    String styleId, MultipartFile file, String token) {
        return ResponseEntity.status(201)
                .body(service().uploadReference(user(token).id(), styleId, file));
    }

    @Override
    public ResponseEntity<Void> deleteReferenceApiV1StylesStyleIdReferencesReferenceIdDelete(
            String styleId, String referenceId, String token) {
        service().deleteReference(user(token).id(), styleId, referenceId);
        return ResponseEntity.noContent().build();
    }

    @Override
    public ResponseEntity<PortraitAcceptedResponse> createPortraitApiV1StylesStyleIdPortraitPost(
            String styleId, String token) {
        return ResponseEntity.status(202)
                .body(service().createPortrait(user(token).id(), styleId, null));
    }

    @Override
    public ResponseEntity<PortraitAcceptedResponse>
            createSectionPortraitApiV1StylesStyleIdSectionsSectionPortraitPost(
                    String styleId, String section, String token) {
        return ResponseEntity.status(202)
                .body(service().createPortrait(
                        user(token).id(), styleId, PortraitSection.from(section)));
    }

    @Override
    public ResponseEntity<PortraitTaskResponse> getPortraitTaskApiV1PortraitTasksTaskIdGet(
            String taskId, String token) {
        return ResponseEntity.ok(service().getPortraitTask(user(token).id(), taskId));
    }

    @Override
    public ResponseEntity<StyleResponse> updateSectionApiV1StylesStyleIdSectionsSectionPatch(
            String styleId,
            String section,
            UpdatePortraitSectionRequest request,
            String token) {
        return ResponseEntity.ok(service().updateSection(
                user(token).id(), styleId, PortraitSection.from(section), request));
    }

    @Override
    public ResponseEntity<ApplyStyleResponse> applyStyleApiV1NovelsNovelIdAppliedStylePatch(
            String novelId, ApplyStyleRequest request, String token) {
        return ResponseEntity.ok(service().applyStyle(user(token).id(), novelId, request));
    }

    @Override
    public ResponseEntity<PortraitTaskResponse>
            markProcessingInternalV1StylesStyleIdPortraitTasksTaskIdProcessingPut(
                    String styleId, String taskId, PortraitProcessingRequest request) {
        authenticate(styleId, taskId, request.getRunId());
        return ResponseEntity.ok(service().markProcessing(styleId, taskId, request));
    }

    @Override
    public ResponseEntity<PortraitContextResponse>
            getPortraitContextInternalV1StylesStyleIdPortraitTasksTaskIdPortraitContextPost(
                    String styleId, String taskId, PortraitContextRequest request) {
        authenticate(styleId, taskId, request.getRunId());
        return ResponseEntity.ok(service().portraitContext(styleId, taskId));
    }

    @Override
    public ResponseEntity<PortraitTaskResponse>
            completePortraitInternalV1StylesStyleIdPortraitTasksTaskIdSuccessPut(
                    String styleId, String taskId, Body1 request) {
        authenticate(styleId, taskId, runId(request));
        return ResponseEntity.ok(service().completePortrait(styleId, taskId, request));
    }

    @Override
    public ResponseEntity<PortraitTaskResponse>
            failPortraitInternalV1StylesStyleIdPortraitTasksTaskIdFailurePut(
                    String styleId, String taskId, PortraitFailureRequest request) {
        authenticate(styleId, taskId, request.getRunId());
        return ResponseEntity.ok(service().failPortrait(styleId, taskId, request));
    }

    private void authenticate(String styleId, String taskId, String runId) {
        InternalServiceAuthenticator authenticator = configuredAuthenticator.orElseThrow(() ->
                new ApiException(
                        503,
                        "PORTRAIT_CALLBACK_AUTH_UNAVAILABLE",
                        "画像回调认证暂时不可用"));
        authenticator.authenticate(
                currentRequest(),
                RawRequestBody.current(),
                ServiceScope.PORTRAIT_WRITE,
                taskId,
                runId,
                "style:" + styleId,
                "PORTRAIT_CALLBACK_AUTH_UNAVAILABLE",
                "画像回调认证暂时不可用");
    }

    private StyleService service() {
        return configuredService.orElseThrow(() -> new ApiException(
                503, "STYLE_SERVICE_UNAVAILABLE", "文风服务暂时不可用"));
    }

    private AuthenticatedUser user(String token) {
        return configuredUsers.orElseThrow(() ->
                        new ApiException(503, "AUTH_UNAVAILABLE", "认证服务暂时不可用"))
                .require(token);
    }

    private static String runId(Body1 request) {
        if (request instanceof FullPortraitSuccessRequest full) return full.getRunId();
        if (request instanceof SectionPortraitSuccessRequest section) return section.getRunId();
        throw new ApiException(422, "VALIDATION_ERROR", "画像成功结果类型无效");
    }

    private static HttpServletRequest currentRequest() {
        if (RequestContextHolder.getRequestAttributes()
                instanceof ServletRequestAttributes attributes) {
            return attributes.getRequest();
        }
        throw new ApiException(500, "REQUEST_CONTEXT_UNAVAILABLE", "内部请求上下文不可用");
    }
}
