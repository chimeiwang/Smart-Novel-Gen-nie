package cn.inkforge.serviceauth;

/** 已通过签名、请求绑定、权限、资源和重放校验的服务请求。 */
public record VerifiedServiceRequest(ServiceJwtClaims claims) {}
