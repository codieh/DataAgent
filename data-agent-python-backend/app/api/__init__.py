"""HTTP API 适配层。

承载把应用层 / 领域层能力暴露为 REST 接口所需的所有组件：路由（routes）、
依赖注入（dependencies）、错误处理器（errors）、视图模型（schemas）与
展示转换（presenters）。本包对外只暴露一个包级 docstring，具体装配在
``router`` 与 ``install_error_handlers`` 中完成。
"""

