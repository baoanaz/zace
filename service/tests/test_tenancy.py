"""TASK-061 验收：租户双层（token → user → owns project；D-36 逻辑授权层）。

对应卡内 §C 的**逐端点**清单与 DoD 的可测项。本文件是 TASK-061 的**补做验收**：
该卡的 ``metadb.claim_project/owns_project/list_projects`` 由 TASK-060 产出、``resolve`` 处的
claim 由 TASK-085 补上，但 ``require_project_id`` 的**归属校验**与其余入口一直没接线 ——
也就是 TASK-051 A1 的越权面（任何登录用户可访问任何 projectId）。

覆盖矩阵（逐端点，**不许只测一个**）：

| §C 端点 | 越权（B 访问 A 的项目） | 用例 |
|---|---|---|
| ``GET /api/projects`` | 只看到自己的项目 | ``test_list_projects_only_shows_owned`` |
| ``GET /api/projects/{id}`` | 404 | ``test_cross_user_endpoints_are_404`` |
| ``DELETE /api/projects/{id}`` | 404（A 的项目仍在） | ``test_cross_user_delete_is_404`` |
| ``GET /api/sync/status/{projectId}`` | 404 | ``test_cross_user_endpoints_are_404`` |
| ``POST /api/sync/batch-upload`` | 404（不得隐式 claim） | ``test_batch_upload_never_claims`` |
| ``POST /api/sync/checkpoint`` | 404 | ``test_cross_user_endpoints_are_404`` |
| ``POST /api/sync/deletions`` | 404 | ``test_cross_user_endpoints_are_404`` |
| ``POST /api/query/search`` | 404 | ``test_cross_user_endpoints_are_404`` |
| ``POST /api/query/ask`` | 404 | ``test_cross_user_endpoints_are_404`` |
| ``GET /api/usage/projects/{id}`` | 404 | ``test_cross_user_endpoints_are_404`` |
| ``GET /api/projects/{id}/index-runs`` | 404 | ``test_cross_user_endpoints_are_404`` |
| ``GET /api/projects/{id}/index-stats`` | 404 | ``test_cross_user_endpoints_are_404`` |
| ``mcp.py::_project_id_for`` | **未接**（卡内自相矛盾） | 无（登记为未决问题） |

其余 DoD 项：归属的产生（``attach`` / ``resolve`` 的 claim、幂等）、``GET /api/projects`` 过滤、
本地模式回归（R34）、以及跨用户共用同一 identityKey 的既定简化。

纪律：``tmp_path`` 下的临时 data_root + 确定性假 provider，不联网、不加载真实模型。
"""

from __future__ import annotations

import base64
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from zace_core.engine import Engine
from zace_core.hashing import blob_hash
from zace_service.app import create_app
from zace_service.config import Settings
from zace_service.metadb import MetaDB
from zace_service.runtime import EngineManager

from tests.conftest import (
    SAMPLE_FILES,
    SAMPLE_MODULE_PATH,
    DeterministicBigramEmbedding,
    make_client,
)

PASSWORD = "correct-horse-battery"


# --------------------------------------------------------------------------- 夹具


def _build(tmp_path: Path, *, local_mode: bool) -> SimpleNamespace:
    """构造云端/本地形态的应用（注入确定性假 provider 的 manager）。"""
    settings = Settings(
        data_root=tmp_path / "data",
        local_mode=local_mode,
        register_open=True,  # 便于用例注册第二个用户（bootstrap 只给第一个）
        local_rescan_interval_s=0.0,
    )
    app = create_app(settings)
    manager = EngineManager.open(
        settings.data_root,
        engine_factory=lambda root: Engine.open(root, provider=DeterministicBigramEmbedding()),
    )
    manager.attach_meta_db(app.state.meta_db)
    app.state.engine_manager = manager
    return SimpleNamespace(app=app, manager=manager, settings=settings)


def _token(client: TestClient, name: str) -> dict[str, str]:
    """为**当前会话身份**签一个 API Key，返回可复用的 Authorization 头。"""
    created = client.post("/api/auth/tokens", json={"name": name})
    assert created.status_code == 200, created.text
    return {"Authorization": f"Bearer {created.json()['token']}"}


def _blobs(files: dict[str, str]) -> list[dict[str, str]]:
    return [
        {
            "path": path,
            "blobHash": blob_hash(path, content.encode("utf-8")),
            "contentB64": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        }
        for path, content in files.items()
    ]


@pytest.fixture
def two_users(tmp_path: Path) -> Iterator[SimpleNamespace]:
    """云端形态、两个**真实**用户（A / B），各自 resolve 了一个项目。

    为什么用 API Key 而不是 session cookie：``TestClient`` 只有一个 cookie jar，注册 B 会覆盖
    A 的会话 cookie；用两个 Bearer 头才能在同一客户端上干净地切换身份。
    """
    ns = _build(tmp_path, local_mode=False)
    ns.client = make_client(ns.app)
    with ns.client:
        bootstrap = ns.client.post(
            "/api/auth/bootstrap", json={"name": "alice", "password": PASSWORD}
        )
        assert bootstrap.status_code == 201, bootstrap.text
        ns.alice_id = bootstrap.json()["userId"]
        ns.alice = _token(ns.client, "alice-key")

        registered = ns.client.post(
            "/api/auth/register", json={"name": "bob", "password": PASSWORD}
        )
        assert registered.status_code == 201, registered.text
        ns.bob_id = registered.json()["userId"]
        ns.bob = _token(ns.client, "bob-key")

        ns.alice_project = ns.client.post(
            "/api/projects/resolve",
            json={"identityKey": "identity:alice-repo", "displayName": "alice-repo"},
            headers=ns.alice,
        ).json()["projectId"]
        ns.bob_project = ns.client.post(
            "/api/projects/resolve",
            json={"identityKey": "identity:bob-repo", "displayName": "bob-repo"},
            headers=ns.bob,
        ).json()["projectId"]
        ns.meta_db = ns.app.state.meta_db
        yield ns
    ns.manager.close()


# --------------------------------------------------------------------------- §C 逐端点：越权 → 404


#: §C 清单里全部消费 ``projectId`` 的端点（``rescan`` 仅本地模式 → 非越权面，不在此列）。
CROSS_USER_CALLS: list[tuple[str, str, dict[str, object]]] = [
    ("get", "/api/projects/{pid}", {}),
    ("get", "/api/sync/status/{pid}", {}),
    ("post", "/api/sync/batch-upload", {"blobs": []}),
    ("post", "/api/sync/checkpoint", {"blobHashes": []}),
    ("post", "/api/sync/deletions", {"paths": []}),
    ("post", "/api/query/search", {"query": "令牌过期后在哪里刷新"}),
    ("post", "/api/query/ask", {"question": "令牌过期后在哪里刷新"}),
    ("get", "/api/usage/projects/{pid}", {}),
    ("get", "/api/projects/{pid}/index-runs", {}),
    ("get", "/api/projects/{pid}/index-stats", {}),
]


@pytest.mark.parametrize(
    "method,path,body", CROSS_USER_CALLS, ids=[f"{m.upper()} {p}" for m, p, _ in CROSS_USER_CALLS]
)
def test_cross_user_endpoints_are_404(
    two_users: SimpleNamespace, method: str, path: str, body: dict[str, object]
) -> None:
    """B 访问 A 的 projectId → **404 project_not_found**（逐端点，**不是 403**）。

    为什么必须是 404 而不是 403：403 会泄露"这个 projectId 存在"，与 Module/06 §2.2 的
    "不给探测面"冲突（卡内 §C 已裁定）。因此越权与"真不存在"用**同一个 code 与状态码**。
    """
    url = path.format(pid=two_users.alice_project)
    payload = {"projectId": two_users.alice_project, **body} if method == "post" else None
    response = two_users.client.request(
        method, url, json=payload, headers=two_users.bob
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "project_not_found"


def test_cross_user_delete_is_404(two_users: SimpleNamespace) -> None:
    """B ``DELETE`` A 的项目 → 404，且 A 的项目**必须还在**（拒绝删除，不是静默成功）。"""
    url = f"/api/projects/{two_users.alice_project}"
    assert two_users.client.delete(url, headers=two_users.bob).status_code == 404
    assert two_users.client.get(url, headers=two_users.alice).status_code == 200


def test_owner_access_is_unaffected(two_users: SimpleNamespace) -> None:
    """同一批端点上，**归属者自己**访问照常 200（归属校验没有误伤）。"""
    for method, path in [
        ("get", "/api/projects/{pid}"),
        ("get", "/api/sync/status/{pid}"),
        ("get", "/api/usage/projects/{pid}"),
        ("get", "/api/projects/{pid}/index-runs"),
        ("get", "/api/projects/{pid}/index-stats"),
    ]:
        response = two_users.client.request(
            method, path.format(pid=two_users.alice_project), headers=two_users.alice
        )
        assert response.status_code == 200, f"{method} {path}: {response.text}"


def test_cross_user_rescan_is_local_mode_403_not_a_leak(two_users: SimpleNamespace) -> None:
    """``rescan`` 仅本地模式：云端对任何人都是 403 ``local_mode_required``（非越权面）。

    顺序纪律：能力检查（403）先于归属检查（404），因此它不会变成"存在性探针"。
    """
    response = two_users.client.post(
        f"/api/projects/{two_users.alice_project}/rescan", headers=two_users.bob
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "local_mode_required"


# --------------------------------------------------------------- §C：GET /api/projects 过滤


def test_list_projects_only_shows_owned(two_users: SimpleNamespace) -> None:
    """``GET /api/projects`` 只返回当前用户的项目（**不是** manager 的全量）。"""
    alice = two_users.client.get("/api/projects", headers=two_users.alice).json()
    bob = two_users.client.get("/api/projects", headers=two_users.bob).json()

    assert [item["projectId"] for item in alice] == [two_users.alice_project]
    assert [item["projectId"] for item in bob] == [two_users.bob_project]


# --------------------------------------------------------------------------- §B：归属的产生


def test_batch_upload_never_claims(two_users: SimpleNamespace) -> None:
    """``batch-upload`` 到**未归属**当前用户的 projectId → 404，且**不得**隐式 claim。

    为什么是 404 而不是卡内 §B 原文的 403：见 :func:`test_cross_user_endpoints_are_404` 的
    理由（§C 的"不给探测面"口径优先）。

    为什么绝不能隐式 claim：``projectId`` 是 ``sha256(identity)``（D-29），同仓库的他人**算得出**
    同一 id；一旦"知道 id 就能抢注"，归属就失去意义（卡内 §B 明令"不得"）。
    """
    payload = {"projectId": two_users.alice_project, "blobs": _blobs(SAMPLE_FILES)}
    response = two_users.client.post(
        "/api/sync/batch-upload", json=payload, headers=two_users.bob
    )
    assert response.status_code == 404
    assert two_users.meta_db.list_projects(two_users.bob_id) == [two_users.bob_project]


def test_upload_by_owner_indexes_and_is_searchable(two_users: SimpleNamespace) -> None:
    """归属者上传自己的项目 → 200；B 检索自己的项目正常（"B 自己的项目正常"）。"""
    uploaded = two_users.client.post(
        "/api/sync/batch-upload",
        json={"projectId": two_users.bob_project, "blobs": _blobs(SAMPLE_FILES)},
        headers=two_users.bob,
    )
    assert uploaded.status_code == 200, uploaded.text

    found = two_users.client.post(
        "/api/query/search",
        json={"projectId": two_users.bob_project, "query": "令牌过期后在哪里刷新"},
        headers=two_users.bob,
    )
    assert found.status_code == 200, found.text
    assert SAMPLE_MODULE_PATH in found.json()["markdown"]


def test_resolve_claims_and_is_idempotent(two_users: SimpleNamespace) -> None:
    """同一用户重复 resolve 同一 identityKey → 幂等（不产生第二行、不报错）。"""
    first = two_users.client.post(
        "/api/projects/resolve",
        json={"identityKey": "identity:alice-repo", "displayName": "alice-repo"},
        headers=two_users.alice,
    ).json()
    assert first == {"projectId": two_users.alice_project, "created": False}
    assert two_users.meta_db.list_projects(two_users.alice_id) == [two_users.alice_project]


def test_shared_repo_second_user_resolves_but_does_not_take_over(
    two_users: SimpleNamespace,
) -> None:
    """**共用仓库的既定简化**（卡内 §B 要求明确写出）：第二人 resolve 不报错、也不获得归属。

    本项目常见形态是多人共用同一仓库（同一 identityKey → 同一 projectId）。TASK-061 §A0 已裁定
    口径 A：``resolve`` **不**报 403 ``project_owned_by_other``（否则会把第二人直接卡死），
    越权一律由 §C 的 404 拦。代价是第二人 resolve 成功但项目不在其名下 —— 这正是"先到先得"的
    V1 简化：``org_id`` 列留待 V2 做共享（Module/06 §2.3）。
    """
    response = two_users.client.post(
        "/api/projects/resolve",
        json={"identityKey": "identity:alice-repo", "displayName": "alice-repo"},
        headers=two_users.bob,
    )
    assert response.status_code == 200, response.text
    assert response.json()["projectId"] == two_users.alice_project  # 同一 identity → 同一 id
    # 归属没有转移，也没有产生第二行。
    assert two_users.meta_db.list_projects(two_users.alice_id) == [two_users.alice_project]
    assert two_users.meta_db.list_projects(two_users.bob_id) == [two_users.bob_project]
    # 第二人随后访问该项目 → 404（§C 的归属校验生效）。
    assert (
        two_users.client.get(
            f"/api/projects/{two_users.alice_project}", headers=two_users.bob
        ).status_code
        == 404
    )


# --------------------------------------------------------------------------- §B：attach 的 claim


def test_attach_claims_to_the_local_user(tmp_path: Path) -> None:
    """本地模式 + 已注入 MetaDB（``zace-service local`` 的真实路径）→ attach 认领给本地用户。

    §B 第二行要求 ``attach`` 认领给 ``is_local=1`` 的本地用户。本地模式默认没有账户体系
    （R34），因此这里在**元数据库已存在**时取/建一个 ``local`` 隐式账户再写归属。
    """
    from zace_service.auth import LOCAL_USER_NAME

    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / SAMPLE_MODULE_PATH.replace("src/", "")).write_text(
        SAMPLE_FILES[SAMPLE_MODULE_PATH], encoding="utf-8"
    )
    settings = Settings(
        data_root=tmp_path / "data", local_mode=True, local_rescan_interval_s=0.0
    )
    app = create_app(settings)
    manager = EngineManager.open(
        settings.data_root,
        engine_factory=lambda r: Engine.open(r, provider=DeterministicBigramEmbedding()),
    )
    # 与 ``__main__._run_local`` 一致：本地模式由启动路径显式注入 MetaDB。
    db = MetaDB.open(settings.meta_db_path)
    manager.attach_meta_db(db)
    app.state.meta_db = db
    app.state.engine_manager = manager

    client = make_client(app)
    with client:
        attached = client.post(
            "/api/projects/attach", json={"root": str(repo), "displayName": "repo"}
        )
        assert attached.status_code == 200, attached.text
        project_id = attached.json()["projectId"]
    assert db.list_projects(db.ensure_local_user().id) == [project_id]
    assert db.get_user_by_name(LOCAL_USER_NAME) is not None
    manager.close()


def test_attach_does_not_create_meta_db_in_default_local_mode(tmp_path: Path) -> None:
    """默认本地模式（app 级无 MetaDB）→ attach **不建库、不写归属**（R34 回归保护）。

    与 :func:`test_attach_claims_to_the_local_user` 合起来钉住边界：认领只在"库已存在"时发生，
    默认本地单用户模式的行为与今天逐字一致（``zace-meta.db`` 不被顺手创建）。
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
    settings = Settings(
        data_root=tmp_path / "data", local_mode=True, local_rescan_interval_s=0.0
    )
    app = create_app(settings)
    manager = EngineManager.open(
        settings.data_root,
        engine_factory=lambda r: Engine.open(r, provider=DeterministicBigramEmbedding()),
    )
    app.state.engine_manager = manager
    assert app.state.meta_db is None
    with make_client(app) as client:
        assert client.post("/api/projects/attach", json={"root": str(repo)}).status_code == 200
    assert app.state.meta_db is None, "本地模式不该因为 attach 而创建 zace-meta.db"
    assert not settings.meta_db_path.exists(), "磁盘上也不该出现 zace-meta.db"
    manager.close()


# --------------------------------------------------------------- §D：本地模式回归（R34）


def test_local_mode_ignores_ownership_entirely(tmp_path: Path) -> None:
    """本地模式（无 ``zace_user``）：不带任何凭据即可访问全部端点，行为与今天一致（R34）。"""
    settings = Settings(
        data_root=tmp_path / "data", local_mode=True, local_rescan_interval_s=0.0
    )
    app = create_app(settings)
    manager = EngineManager.open(
        settings.data_root,
        engine_factory=lambda r: Engine.open(r, provider=DeterministicBigramEmbedding()),
    )
    app.state.engine_manager = manager
    with make_client(app) as client:
        resolved = client.post(
            "/api/projects/resolve", json={"identityKey": "identity:local-only"}
        ).json()
        project_id = resolved["projectId"]
        assert client.get("/api/projects").status_code == 200
        assert client.get(f"/api/projects/{project_id}").status_code == 200
        assert client.get(f"/api/sync/status/{project_id}").status_code == 200
        assert client.post(
            "/api/sync/batch-upload",
            json={"projectId": project_id, "blobs": _blobs(SAMPLE_FILES)},
        ).status_code == 200
    manager.close()


# --------------------------------------------------------------------------- 未接线说明


def test_mcp_face_ownership_is_not_wired_yet(two_users: SimpleNamespace) -> None:
    """**登记未接通**：``mcp.py`` 的 ``_project_id_for`` 只判"项目存在"，**不判归属**。

    卡内 §C 点名"MCP 面同样要过归属校验"，但卡内「交付物所有权」清单**不含** ``mcp.py``
    （§A0 的"剩余"列也只列了 ``routers/{projects,sync,query,ops}.py``）——两者自相矛盾。
    本用例**不断言越权成功**（那会把缺口固化成契约），只钉住"当前 MCP 面拿不到 HTTP 请求里的
    ``zace_user``"这一实现事实，作为未决问题的可执行证据：要接上，必须先给 MCP 工具一条
    身份传递通道（contextvar 或按 Bearer 重解析），属跨卡改动。
    """
    from zace_service.mcp import manager_for_app

    # MCP 工具没有 ``Request``（见 ``mcp.py`` 的 ``manager_for_app`` 注释）：它只拿到 manager，
    # 因此今天无从得知"当前用户是谁"——这正是归属校验无法就地接入的原因。
    manager = manager_for_app(two_users.app)
    assert manager.project_exists(two_users.alice_project), (
        "MCP 面只能看到项目是否存在；归属不在其可见范围内（待接线）"
    )
