# 架构

项目整体架构说明，涉及 TokenService 与 `refresh_token`。

## 认证模块

认证模块负责 token 生命周期管理。

### token 刷新流程

刷新流程如下：

```python
def refresh_token(service):
    # 这是围栏内的注释，不是标题
    return service.refresh()
```

### 会话管理

会话缓存，见 `SessionStore`。

```
plain fence without language
```

## 认证模块

第二个同名小节，用于验证 start_line 消歧。

```text
# 围栏内的伪标题
```
