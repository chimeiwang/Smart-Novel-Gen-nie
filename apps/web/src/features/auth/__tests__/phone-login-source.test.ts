import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("手机号入口必须由双开关和公开验证码配置共同控制", async () => {
  const pageUrl = new URL("../../../app/login/page.tsx", import.meta.url);
  const source = await readFile(pageUrl, "utf8");

  assert.match(source, /PHONE_AUTH_ENABLED.*=== "true"/);
  assert.match(source, /PHONE_AUTH_SEND_ENABLED.*=== "true"/);
  assert.match(source, /captchaPrefix && captchaSceneId/);
  assert.doesNotMatch(source, /ALIYUN_ACCESS_KEY|PHONE_AUTH_HMAC_SECRET/);
});

test("手机号登录保留自动建号说明、协议同意和老账号边界", async () => {
  const formUrl = new URL("../login-form.tsx", import.meta.url);
  const source = await readFile(formUrl, "utf8");

  assert.match(source, /未注册手机号验证后将自动创建账号/);
  assert.match(source, /acceptedTerms,/);
  assert.match(source, /手机号不会自动绑定旧账号/);
  assert.match(source, /role="tablist"/);
  assert.match(source, />\s*手机号登录\s*</);
  assert.match(source, />\s*原账号登录\s*</);
  assert.match(source, /原账号无需绑定手机号/);
  assert.match(source, /\/api\/v1\/auth\/phone\/challenges/);
  assert.match(source, /\^\\d\{6\}\$/);
  assert.doesNotMatch(source, /ALIYUN_ACCESS_KEY|PHONE_AUTH_HMAC_SECRET/);
});

test("公开协议必须展示确认后的主体与联系邮箱", async () => {
  const termsUrl = new URL("../../../app/terms/page.tsx", import.meta.url);
  const privacyUrl = new URL("../../../app/privacy/page.tsx", import.meta.url);
  const sources = await Promise.all([
    readFile(termsUrl, "utf8"),
    readFile(privacyUrl, "utf8"),
  ]);

  for (const source of sources) {
    assert.match(source, /重庆市创煜新软件有限公司/);
    assert.match(source, /mailto:niebqoiang@gmail\.com/);
    assert.doesNotMatch(source, /仍须公布真实可用/);
  }
});

test("验证码 V3 参数使用后必须重新初始化且只动态加载官方脚本", async () => {
  const formUrl = new URL("../login-form.tsx", import.meta.url);
  const source = await readFile(formUrl, "utf8");

  assert.match(
    source,
    /https:\/\/o\.alicdn\.com\/captcha-frontend\/aliyunCaptcha\/AliyunCaptcha\.js/,
  );
  assert.match(source, /setCaptchaEpoch\(\(value\) => value \+ 1\)/);
  assert.match(source, /\[captchaEpoch, phoneAuth\]/);
  assert.equal(source.match(/document\.createElement\("script"\)/g)?.length, 1);
});
