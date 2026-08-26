/** 小说到视频的项目、章节改编、视觉设定、逐镜渲染和后期制作控制面。 */
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = {"db", "generated", "identity::authentication", "platform"})
package cn.inkforge.core.video;
