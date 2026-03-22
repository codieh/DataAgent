# Spring WebFlux 学习指南

## 一、学习路径

### 1. 前置知识准备

在学习 Spring WebFlux 之前，你需要掌握以下知识：

- Java 8 特性，尤其是 Lambda 表达式和流式编程

- Spring Boot 基础开发能力

- 响应式编程的基本概念（异步非阻塞、背压机制）

### 2. 基础入门阶段

#### （1）核心概念理解

Spring WebFlux 是 Spring Framework 5.0 引入的响应式 Web 框架，基于 Reactor 库实现，核心是两个异步序列类型：

- **Mono**：表示 0 或 1 个元素的异步序列，适用于单个结果的场景，比如查询单个用户信息、执行更新操作

- **Flux**：表示 0 到 N 个元素的异步序列，适用于多个结果的场景，比如查询用户列表、实时数据流处理

#### （2）两种编程模型

Spring WebFlux 支持两种编程模型：

1. **注解式控制器**：与 Spring MVC 风格类似，使用`@RestController`、`@GetMapping`等注解定义接口，返回值为 Mono 或 Flux 类型

```java

@RestController
@RequestMapping("/api/users")
public class UserController {
    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    @GetMapping("/{id}")
    public Mono<User> getUserById(@PathVariable Long id) {
        return userService.getUserById(id);
    }

    @GetMapping
    public Flux<User> getAllUsers() {
        return userService.getAllUsers();
    }
}
```

1. **函数式端点**：基于 Java 8 Lambda 表达式，采用路由 - 处理器模式定义接口

```java

@Configuration
public class UserRouterConfig {
    @Bean
    public RouterFunction<ServerResponse> userRouter(UserHandler userHandler) {
        return RouterFunctions.route()
                .GET("/api/func/users/{id}", userHandler::getUserById)
                .GET("/api/func/users", userHandler::getAllUsers)
                .POST("/api/func/users", userHandler::createUser)
                .build();
    }
}

@Component
public class UserHandler {
    private final UserService userService;

    public UserHandler(UserService userService) {
        this.userService = userService;
    }

    public Mono<ServerResponse> getUserById(ServerRequest request) {
        Long id = Long.valueOf(request.pathVariable("id"));
        return ServerResponse.ok()
                .body(userService.getUserById(id), User.class);
    }
}
```

### 3. 实战开发阶段

#### （1）环境搭建

在 Spring Boot 项目中引入 WebFlux 依赖：

```xml

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

#### （2）响应式数据访问

- **关系型数据库**：使用 R2DBC（Reactive Relational Database Connectivity），引入依赖：

```xml

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-r2dbc</artifactId>
</dependency>
<dependency>
    <groupId>io.r2dbc</groupId>
    <artifactId>r2dbc-h2</artifactId>
    <scope>runtime</scope>
</dependency>
```

定义响应式 Repository：

```java

public interface UserRepository extends ReactiveCrudRepository<User, Long> {
    Flux<User> findByUsernameLike(String username);
}
```

- **NoSQL 数据库**：使用 Reactive MongoDB，引入依赖：

```xml

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
</dependency>
```

定义响应式 Repository：

```java

public interface UserRepository extends ReactiveMongoRepository<User, String> {
    Mono<User> findByEmail(String email);
}
```

#### （3）响应式 HTTP 客户端

使用 WebClient 替代 RestTemplate，实现异步非阻塞的 HTTP 调用：

```java

@Service
public class OrderService {
    private final WebClient webClient;

    public OrderService(WebClient.Builder webClientBuilder) {
        this.webClient = webClientBuilder.baseUrl("http://user-service/api/users").build();
    }

    public Mono<User> getUserById(Long id) {
        return webClient.get()
                .uri("/{id}", id)
                .retrieve()
                .bodyToMono(User.class);
    }
}
```

### 4. 高级特性

- **服务器发送事件（SSE）**：实现服务器主动向客户端推送数据

```java

@GetMapping(value = "/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<String> streamEvents() {
    return Flux.interval(Duration.ofSeconds(1))
            .map(sequence -> "Event: " + sequence);
}
```

- **WebSocket 通信**：实现双向实时通信

- **响应式安全集成**：使用 Spring Security WebFlux 实现权限校验

## 二、学习资源

### 1. 官方文档

- [Spring WebFlux 官方文档](https://docs.spring.io/spring-framework/docs/current/reference/html/web-reactive.html#webflux-controller)

- [Spring Boot 响应式应用文档](https://www.spring-doc.cn/spring-boot/3.4.5-SNAPSHOT/reference_web_reactive.en.html)

### 2. 详细教程

- [《响应式编程新篇章：深入 Spring WebFlux》](https://blog.csdn.net/2301_81152266/article/details/156394907)

### 3. 视频教程

- [Java 编程方法论 - 响应式编 - Reactor](https://www.bilibili.com/video/av35326911)

- [WebFlux 系列教程](https://www.bilibili.com/video/av82028626)

- [尚硅谷 SpringBoot3 响应式编程](http://m.atguigu.com/video/detail/286/)

## 三、适用场景

Spring WebFlux 适用于以下场景：

1. 高并发 API 网关，处理大量请求转发

2. 实时数据推送应用，如股票行情、物联网数据采集

3. 大数据处理应用，需要异步处理大量数据流

4. 资源受限的环境，需要高效利用系统资源

注意：Spring WebFlux 并非 Spring MVC 的替代者，而是对 Spring 生态的补充，在低并发场景下，Spring MVC 的性能表现可能更好，选择时需要根据实际业务场景判断。
> （注：文档部分内容可能由 AI 生成）