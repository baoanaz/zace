## Relevant Context
### Code
[E1] TokenService.refresh — src/auth/token_service.py:45-46
     reason: explicit symbol TokenService.refresh + 3-channel consensus +0.5
     45 | def refresh(self):
     46 |     return self.store.rotate()
[E2] TokenStore.rotate — src/store.py:210-212
     reason: bm25 -1.2 + vector 0.81
     210 | def rotate(self):
     211 |     return 'rotated'
[E3] AuthMiddleware.verify — src/mw.py:88-89
     reason: bm25 -1.0 + vector 0.77
     88 | def verify(self, request):
     89 |     return refresh()
### Flow
[F1] AuthMiddleware.verify → TokenService.refresh
### Docs
[E4] docs/design/auth.md > 认证 > Token Refresh（design）
     reason: bm25 -2.1 + high-value doctype +0.8
     30 | 刷新流程说明
     31 | 
     32 | 使用 refresh_token
     ⚠ 引用了已删除符号 LegacyToken.rotate，文档可能过时
### Missing Evidence
- [index_stale] 索引落后于工作区：1 个文件已变更但未重索引，证据可能不是当前代码。
- [unresolved_reference] 2 个符号引用无法解析（unresolved_refs status=failed），涉及这些符号的调用关系可能缺失。
- [stale_doc_reference] (LegacyToken.rotate) 文档 docs/design/auth.md 引用了已删除或改名的符号（LegacyToken.rotate），该文档可能已过时；需要以代码为准并更新文档。
### Meta
confidence: high | index: stale (1 files) | budget: 574/10.0K
