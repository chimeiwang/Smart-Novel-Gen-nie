# ADR-001：Java Core 技术栈

日期：2026-08-24

状态：已接受

## 背景

Core 需要完整替换 FastAPI，同时保持单机 2 核 2 GB、448 MB Core 容器、PostgreSQL 14、Redis、
FFmpeg 和 Python Agent 的现有边界。迁移目的是获得成熟的 Java 业务基础并实践 TDD，不是拆微服务。

## 决策

- 使用 Java 21 LTS；
- 使用当前稳定 Spring Boot 4.1.1，不使用 milestone 或 snapshot；
- 使用 Maven 3.9.11 Wrapper 和根聚合 POM；
- 使用 Spring MVC、Security、Validation、Actuator，不使用 WebFlux/R2DBC；
- 使用 jOOQ、PostgreSQL JDBC 和 HikariCP，不使用 JPA/Hibernate 自动映射业务结构；
- 使用 Spring Data Redis/Lettuce；
- 使用 Spring Modulith 2.1.0 和 ArchUnit 约束单体模块边界；
- 使用 JUnit 5、AssertJ、MockMvc、Testcontainers、WireMock 和 JaCoCo；
- 媒体进程使用 `ProcessBuilder` 参数数组，禁止 shell 拼接。

Spring Boot 官方文档在本决策日期列出 4.1.1 为稳定版本，要求 Java 17 以上并支持至 Java 26；项目仍
固定 Java 21，以获得 LTS 运行基线。Spring Modulith 2.1.0 是对应 Boot 4.1 的稳定代际。

## 理由

- Servlet/JDBC 与当前同步事务、文件和 SSE 控制面更直接，减少重写变量；
- jOOQ 能忠实处理 PostgreSQL enum、quoted camelCase、部分索引和复杂约束，避免 ORM 自动 DDL；
- 模块化单体保留一个部署单元，同时能约束领域依赖；
- Maven Wrapper 让本地、CI 和部署构建使用同一 Maven 版本；
- Java 21 在目标服务器资源预算内比引入更激进运行时更可控。

## 后果

- 开发环境必须提供 JDK 21；
- 所有数据库集成测试使用 PostgreSQL，不用 H2；
- 需要显式编写 SQL/jOOQ 映射和事务边界；
- 需要在 448 MB 容器中验证 JVM heap、Metaspace、线程和 FFmpeg 峰值；
- 技术栈版本升级必须单独验证 OpenAPI、Jackson、Tomcat 和 Modulith 行为。

## 官方依据

- [Spring Boot 4.1.1 系统要求](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring Modulith 2.1.0](https://docs.spring.io/spring-modulith/reference/)
- [Apache Maven Wrapper](https://maven.apache.org/tools/mavenwrapper.html)
