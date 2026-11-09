"""Account connections use official programs, scoped profiles and revocable local capabilities."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app import account_cli
from app.auth.context import TenantContext
from app.routers.account_login import CompletionRequest, completion_prompt, response_message, local_only


def test_profile_and_child_environment_are_isolated_without_changing_the_parent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_ACCOUNT_CLI_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "do-not-forward")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "do-not-forward")
    monkeypatch.setenv("GH_TOKEN", "do-not-forward")
    tenant, workspace = uuid4(), uuid4()
    profile = account_cli.profile_for(tenant, workspace, "gemini")
    assert profile != account_cli.profile_for(tenant, uuid4(), "gemini")
    assert profile != account_cli.profile_for(uuid4(), workspace, "gemini")
    env = account_cli.environment(profile, "gemini")
    assert all(key not in env for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GH_TOKEN"))
    assert Path(env["HOME"]).is_relative_to(profile)
    assert env["OTEL_SDK_DISABLED"] == "true"
    assert os.environ["OPENAI_API_KEY"] == "do-not-forward"
    account_cli.prepare(profile, "gemini")
    settings = json.loads((profile / "home/.gemini/antigravity-cli/settings.json").read_text())
    assert "read_file(*)" in settings["permissions"]["deny"] and "command(*)" in settings["permissions"]["deny"]
    assert settings["disableTelemetry"] is True
    assert (profile.stat().st_mode & 0o777) == 0o700
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (profile / "cache").rmdir()
    (profile / "cache").symlink_to(foreign, target_is_directory=True)
    with pytest.raises(account_cli.AccountCliError):
        account_cli.profile_for(tenant, workspace, "gemini")


def test_provider_arguments_disable_native_tools_and_never_interpolate_a_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(account_cli, "executable", lambda provider: "/official/" + provider)
    assert account_cli.command("claude", "login") == ["/official/claude", "auth", "login", "--claudeai"]
    args = account_cli.command("claude", "complete")
    assert args[args.index("--tools") + 1] == ""
    assert "--strict-mcp-config" in args and "--no-session-persistence" in args
    codex = account_cli.command("codex", "complete")
    assert codex[codex.index("--sandbox") + 1] == "read-only" and "features.shell_tool=false" in codex
    assert "dangerously-bypass-approvals-and-sandbox" not in " ".join(codex)
    selected = account_cli.command("codex", "complete", "gpt-sol@high")
    assert selected[selected.index("--model")+1] == "gpt-sol"
    assert 'model_reasoning_effort="high"' in selected
    with pytest.raises(account_cli.AccountCliError,match="Unsupported Codex effort"):
        account_cli.command("codex","complete","gpt-sol@arbitrary")



@pytest.mark.parametrize(("provider", "text", "answer"), [
    ("codex", '{"type":"item.completed","item":{"type":"agent_message","text":"hello"}}\n{"type":"turn.completed","usage":{"input_tokens":12,"output_tokens":3}}', "hello"),
    ("claude", '{"result":"hello","usage":{"input_tokens":12,"output_tokens":3}}', "hello"),
    ("gemini", '{"response":"hello","stats":{"models":{"gemini":{"tokens":{"prompt":12,"candidates":3}}}}}', "hello"),
])
def test_only_final_responses_and_actual_usage_are_extracted(provider: str, text: str, answer: str) -> None:
    parsed = account_cli.parse_output(provider, text)
    assert parsed["content"] == answer
    assert parsed["usage"] == {"prompt_tokens": 12, "completion_tokens": 3}
    for raw in ("not-json", '{"error":"vendor secret details"}', "{}"):
        with pytest.raises(account_cli.AccountCliError) as result:
            account_cli.parse_output(provider, raw)
        assert "vendor secret details" not in str(result.value)


def test_model_can_only_request_declared_functions_and_never_execute_them() -> None:
    tools = [{"type": "function", "function": {"name": "read_report", "parameters": {"type": "object"}}}]
    response = response_message('{"content":null,"tool_calls":[{"name":"read_report","arguments":{"path":"report.csv"}}]}', tools)
    assert json.loads(response["tool_calls"][0]["function"]["arguments"]) == {"path": "report.csv"}
    for raw in ('{"tool_calls":[{"name":"arbitrary_shell","arguments":{}}]}', '{"tool_calls":[{"name":"read_report","arguments":"rm -rf"}]}', 'unexpected text'):
        with pytest.raises(HTTPException) as failure:
            response_message(raw, tools)
        assert failure.value.status_code == 502
    prompt = completion_prompt(CompletionRequest(model="m", messages=[{"role": "user", "content": "x"}], tools=tools))
    assert "do not execute them yourself" in prompt and "read_report" in prompt


def test_account_applications_are_disabled_on_shared_servers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEXUS_LOCAL_MODE", raising=False)
    with pytest.raises(HTTPException) as result:
        local_only()
    assert result.value.status_code == 403


def test_adapter_subprocess_keeps_prompts_on_stdin_and_scrubs_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_ACCOUNT_CLI_DIR", str(tmp_path / "profiles"))
    profile = account_cli.profile_for(uuid4(), uuid4(), "claude")
    import sys
    script = tmp_path / "test-cli.py"
    script.write_text('import sys,json\nvalue=sys.stdin.read()\nprint(json.dumps({"response":value}))\n')
    monkeypatch.setattr(account_cli, "command", lambda *args: [sys.executable, str(script)])
    result = asyncio.run(account_cli.run(profile, "claude", "Literal $(id); `secret`"))
    assert result["content"] == "Literal $(id); `secret`"
    script.write_text('import sys\nprint("sk-private-token",file=sys.stderr)\nsys.exit(3)\n')
    with pytest.raises(account_cli.AccountCliError) as failure:
        asyncio.run(account_cli.run(profile, "claude", "Hello"))
    assert "sk-private-token" not in str(failure.value)


def test_official_claude_rate_limit_is_distinct_from_missing_authentication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    profile = tmp_path
    (profile / "work").mkdir()
    script = tmp_path / "limited.py"
    script.write_text('import json,sys\nprint(json.dumps({"is_error":True,"api_error_status":429,"result":"provider-private-details"}))\nsys.exit(1)\n')
    monkeypatch.setattr(account_cli,"command",lambda *args:[sys.executable,str(script)])
    with pytest.raises(account_cli.AccountCliRateLimited) as failure:
        asyncio.run(account_cli.run(profile,"claude","test"))
    assert "429" in str(failure.value) and "provider-private-details" not in str(failure.value)


def test_browser_login_jobs_are_scoped_to_the_provider_and_can_be_cancelled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.google_account import GoogleLogins
    async def wait(*args: Any) -> None:
        await asyncio.Event().wait()
    monkeypatch.setattr(account_cli,"login",wait)
    async def check() -> None:
        jobs=GoogleLogins()
        first=await jobs.start("tenant","workspace","user",tmp_path,"claude")
        second=await jobs.start("tenant","workspace","user",tmp_path,"codex")
        assert jobs.state(first,"tenant","workspace","user","claude")=="pending"
        assert jobs.state(first,"tenant","workspace","user","codex") is None
        assert not await jobs.cancel(first,"tenant","workspace","other-user","claude")
        await asyncio.sleep(0)
        assert await jobs.cancel(first,"tenant","workspace","user","claude")
        assert jobs.state(first,"tenant","workspace","user","claude")=="cancelled"
        assert jobs.state(second,"tenant","workspace","user","codex")=="pending"
        await jobs.close()
    asyncio.run(check())


def test_runtime_capability_cannot_be_reused_for_a_foreign_workspace_or_after_rotation(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import asynccontextmanager
    from collections.abc import AsyncIterator
    from fastapi import FastAPI, Request
    from app.routers import account_login
    from nexus_model_gateway import CredentialCipher
    tenant, workspace, credential = uuid4(), uuid4(), uuid4()
    secret = f"nx-cli-{tenant.hex}.{workspace.hex}.{credential.hex}.test-secret"
    cipher = CredentialCipher(b"a" * 32)
    row = SimpleNamespace(settings={"auth_kind": "official_cli", "account_provider": "gemini"}, provider="gemini", encrypted_key=cipher.encrypt(secret, tenant, workspace, "gemini"))
    @asynccontextmanager
    async def scoped(engine: Any, tid: Any, wid: Any) -> AsyncIterator[Any]:
        class Session:
            async def scalar(self, query: Any) -> Any:
                return row if (tid, wid) == (tenant, workspace) else None
        yield Session()
    monkeypatch.setenv("NEXUS_LOCAL_MODE", "true")
    monkeypatch.setattr(account_login, "scoped_session", scoped)
    app = FastAPI()
    app.state.services = SimpleNamespace(engine=object(), _store=lambda: SimpleNamespace(_cipher=cipher))
    def request(value: str) -> Request:
        return Request({"type": "http", "app": app, "headers": [(b"authorization", ("Bearer " + value).encode())]})
    assert asyncio.run(account_login.runtime_identity(request(secret))) == (tenant, workspace, "gemini")
    for forged in (secret + "x", secret.replace(workspace.hex, uuid4().hex), secret.replace(tenant.hex, uuid4().hex), "invalid"):
        with pytest.raises(HTTPException) as failure:
            asyncio.run(account_login.runtime_identity(request(forged)))
        assert failure.value.status_code == 401
    row.encrypted_key = cipher.encrypt("rotated-capability", tenant, workspace, "gemini")
    with pytest.raises(HTTPException):
        asyncio.run(account_login.runtime_identity(request(secret)))


def test_selected_account_does_not_fall_back_to_a_paid_api_credential() -> None:
    from nexus_model_gateway.router import resolve_credential
    from typing import cast
    from uuid import UUID
    calls: list[str] = []
    class Store:
        async def resolve_model_credential(self, tenant: UUID, workspace: UUID, provider: str, model: str) -> Any:
            calls.append(model)
            raise LookupError("Account sign-in required")
        async def resolve_default_credential(self, *args: Any) -> Any:
            raise AssertionError("A selected account must never fall back to an API key")
    with pytest.raises(LookupError, match="sign-in required"):
        asyncio.run(resolve_credential(Store(), uuid4(), uuid4(), "gemini", None, account_cli.alias("gemini")))
    assert calls == [account_cli.alias("gemini")]


def test_google_acp_refuses_native_tools_and_collects_only_final_answer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import google_account
    import sys
    monkeypatch.setenv("NEXUS_ACCOUNT_CLI_DIR", str(tmp_path / "profiles"))
    profile = account_cli.profile_for(uuid4(), uuid4(), "gemini")
    script = tmp_path / "acp-fixture"
    script.write_text("#!" + sys.executable + '''
import json,sys
pending=None
for line in sys.stdin:
    message=json.loads(line)
    if message.get('method')=='initialize':
        print(json.dumps({'jsonrpc':'2.0','id':message['id'],'result':{'protocolVersion':1}}),flush=True)
    elif message.get('method')=='authenticate':
        assert message['params']['methodId']=='oauth-personal'
        print(json.dumps({'jsonrpc':'2.0','id':message['id'],'result':{}}),flush=True)
    elif message.get('method')=='session/new':
        print(json.dumps({'jsonrpc':'2.0','id':message['id'],'result':{'sessionId':'own-session','models':{'currentModelId':'gemini-high','availableModels':[{'modelId':'gemini-high','name':'Gemini High'},{'modelId':'gemini-low','name':'Gemini Low'}]}}}),flush=True)
    elif message.get('method')=='session/set_model':
        assert message['params']=={'sessionId':'own-session','modelId':'gemini-low'}
        print(json.dumps({'jsonrpc':'2.0','id':message['id'],'result':{}}),flush=True)
    elif message.get('method')=='session/prompt':
        pending=message['id']
        print(json.dumps({'jsonrpc':'2.0','id':901,'method':'session/request_permission','params':{}}),flush=True)
    elif message.get('id')==901:
        assert message['result']['outcome']['outcome']=='cancelled'
        print(json.dumps({'jsonrpc':'2.0','id':902,'method':'fs/read_text_file','params':{'path':'/private/other-workspace'}}),flush=True)
    elif message.get('id')==902:
        assert message['error']['code']==-32601
        print(json.dumps({'jsonrpc':'2.0','method':'session/update','params':{'update':{'sessionUpdate':'agent_message_chunk','content':{'type':'text','text':'VERIFIED_ANSWER'}}}}),flush=True)
        print(json.dumps({'jsonrpc':'2.0','id':pending,'result':{'stopReason':'end_turn'}}),flush=True)
''')
    script.chmod(0o700)
    monkeypatch.setattr(google_account, "executable", lambda provider: str(script))
    async def check() -> None:
        async with google_account.GoogleAccount(profile) as client:
            await client.login()
            catalog, default = await client.catalog()
            assert len(catalog) == 2 and default == "gemini-high"
            with pytest.raises(account_cli.AccountCliError, match="no longer available"):
                await client.answer("Unknown model must not reach inference", "arbitrary-model")
            result = await client.answer("Only return the test marker", "gemini-low")
            assert result["content"] == "VERIFIED_ANSWER"
            assert result["usage"] == {"prompt_tokens": 0, "completion_tokens": 0}
        assert client.process is not None and client.process.returncode is not None
    asyncio.run(check())


def test_google_pool_reuses_only_its_workspace_and_closes_idle_or_cancelled_processes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import google_account
    from collections import Counter
    starts: Counter[Path] = Counter()
    stops: Counter[Path] = Counter()
    class Client:
        def __init__(self, profile: Path) -> None:
            self.profile = profile
            self.process = SimpleNamespace(returncode=None)
        async def __aenter__(self) -> Client:
            starts[self.profile] += 1
            return self
        async def close(self) -> None:
            stops[self.profile] += 1
            self.process.returncode = 0
        async def answer(self, prompt: str, model: str) -> dict[str, Any]:
            if prompt == "wait":
                await asyncio.Event().wait()
            await asyncio.sleep(0)
            return {"content": f"{self.profile.name}:{model}:{prompt}"}
    monkeypatch.setattr(google_account, "GoogleAccount", Client)
    async def check() -> None:
        a, b = tmp_path / "workspace-a", tmp_path / "workspace-b"
        pool = google_account.GoogleAccounts(idle_seconds=0.02)
        first, second = await asyncio.gather(pool.answer(a, "one", "low"), pool.answer(a, "two", "high"))
        assert first["content"] == "workspace-a:low:one" and second["content"] == "workspace-a:high:two"
        assert starts[a] == 1
        assert (await pool.answer(b, "three", "low"))["content"] == "workspace-b:low:three"
        assert starts[b] == 1
        waiter = asyncio.create_task(pool.answer(a, "wait"))
        await asyncio.sleep(0)
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
        assert stops[a] == 1
        await pool.answer(a, "after cancellation")
        assert starts[a] == 2
        await asyncio.sleep(0.06)
        assert not pool.entries and stops[a] == 2 and stops[b] == 1
        await pool.answer(a, "before shutdown")
        await pool.close()
        assert starts[a] == stops[a] == 3
        with pytest.raises(account_cli.AccountCliError, match="shutting down"):
            await pool.answer(a, "after shutdown")
    asyncio.run(check())


def test_account_completion_forwards_the_chosen_model_and_rejects_a_different_account(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import FastAPI, Request
    from app.routers import account_login
    tenant, workspace = uuid4(), uuid4()
    calls: list[str] = []
    class Pool:
        async def answer(self, profile: Path, prompt: str, model: str) -> dict[str, Any]:
            calls.append(model)
            assert str(tenant) in str(profile) and str(workspace) in str(profile)
            return {"content": "chosen model answered", "usage": {"prompt_tokens": 0, "completion_tokens": 0}}
    async def identity(request: Request) -> tuple[Any, Any, str]:
        return tenant, workspace, "gemini"
    monkeypatch.setenv("NEXUS_ACCOUNT_CLI_DIR", str(tmp_path))
    monkeypatch.setattr(account_login, "runtime_identity", identity)
    app = FastAPI()
    app.state.google_accounts = Pool()
    request = Request({"type": "http", "app": app, "headers": []})
    async def check() -> None:
        body = CompletionRequest(model=account_cli.alias("gemini", "gemini-low"), messages=[{"role": "user", "content": "hello"}])
        response = await account_login.complete(body, request)
        assert response["model"] == body.model and calls == ["gemini-low"]
        body.model = account_cli.alias("claude")
        with pytest.raises(HTTPException):
            await account_login.complete(body, request)
        assert calls == ["gemini-low"]
    asyncio.run(check())


def test_legacy_google_connection_lists_concrete_models_without_reconnecting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import asynccontextmanager
    from collections.abc import AsyncIterator
    from fastapi import FastAPI, Request
    from app.routers import providers
    tenant, workspace = uuid4(), uuid4()
    row = SimpleNamespace(preset_id="gemini_subscription", name="account:gemini", provider="gemini", settings={"auth_kind":"official_cli","account_provider":"gemini"}, available_models=[account_cli.alias("gemini")], default_models={"orchestrator":account_cli.alias("gemini")})
    @asynccontextmanager
    async def scoped(*args: Any) -> AsyncIterator[Any]:
        class Session:
            async def scalars(self, query: Any) -> Any:
                return SimpleNamespace(all=lambda:[row])
            async def get(self, *args: Any) -> None:
                return None
        yield Session()
    class Pool:
        async def catalog(self, profile: Path) -> tuple[list[dict[str, str]], str]:
            return [{"id":"gemini-flash-high","name":"Gemini Flash (High)"},{"id":"gemini-flash-low","name":"Gemini Flash (Low)"}], "gemini-flash-high"
    monkeypatch.setenv("NEXUS_LOCAL_MODE", "true")
    monkeypatch.setenv("NEXUS_ACCOUNT_CLI_DIR", str(tmp_path))
    monkeypatch.setattr(providers, "scoped_session", scoped)
    app = FastAPI()
    app.state.services = SimpleNamespace(engine=object())
    app.state.google_accounts = Pool()
    request = Request({"type":"http","app":app,"headers":[]})
    result = asyncio.run(providers.chat_models(request, TenantContext(tenant, workspace, uuid4(), "owner")))
    entries: Any = result["models"]
    assert [item["model"] for item in entries] == ["Gemini Flash (High)","Gemini Flash (Low)"]
    assert entries[1]["id"] == "gemini/nexus-account-gemini:gemini-flash-low"
    assert result["default"] == entries[0]["id"]


def test_google_login_flow_is_private_to_its_user_and_shutdown_cancels_waiters(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import google_account
    from typing import Any
    class Waiting:
        def __init__(self, profile: Path) -> None:
            self.profile = profile
        async def __aenter__(self) -> Waiting:
            return self
        async def __aexit__(self, *args: Any) -> None:
            return None
        async def login(self) -> None:
            await asyncio.Event().wait()
    monkeypatch.setattr(google_account, "GoogleAccount", Waiting)
    async def check() -> None:
        registry = google_account.GoogleLogins()
        flow = await registry.start("tenant", "workspace", "user", tmp_path)
        assert registry.state(flow, "tenant", "workspace", "user") == "pending"
        assert registry.state(flow, "tenant", "foreign", "user") is None
        assert registry.state(flow, "tenant", "workspace", "different-user") is None
        await asyncio.sleep(0)
        await registry.close()
        assert registry.state(flow, "tenant", "workspace", "user") == "cancelled"
    asyncio.run(check())


def test_removed_copilot_account_is_not_exposed_or_executable() -> None:
    assert "copilot" not in account_cli.PROVIDERS
    assert account_cli.executable("copilot") is None
    with pytest.raises(ValueError):
        account_cli.profile_for(uuid4(), uuid4(), "copilot")


def test_codex_catalog_comes_from_the_official_protocol_and_cannot_execute_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    from app import account_models
    (tmp_path / "work").mkdir()
    script=tmp_path / "codex-fixture"
    script.write_text("#!"+sys.executable+'''
import sys,json
for line in sys.stdin:
    m=json.loads(line)
    if m.get('method')=='initialize':
        assert m['params']['clientInfo']['name']=='alba_agent'
        print(json.dumps({'id':m['id'],'result':{}}),flush=True)
    elif m.get('method')=='model/list':
        print(json.dumps({'id':901,'method':'item/commandExecution/requestApproval','params':{}}),flush=True)
    elif m.get('id')==901:
        assert m['error']['code']==-32601
        print(json.dumps({'id':2,'result':{'data':[{'model':'gpt-sol','displayName':'GPT Sol','isDefault':True,'defaultReasoningEffort':'low','supportedReasoningEfforts':[{'reasoningEffort':'low'},{'reasoningEffort':'high'}]},{'model':'hidden','hidden':True,'supportedReasoningEfforts':[{'reasoningEffort':'high'}]}]}}),flush=True)
''')
    script.chmod(0o700)
    monkeypatch.setattr(account_models,"executable",lambda provider:str(script))
    models,current=asyncio.run(account_models.read_codex_models(tmp_path))
    assert current=="gpt-sol@low" and models==[{"id":"gpt-sol@low","name":"GPT Sol (Low)"},{"id":"gpt-sol@high","name":"GPT Sol (High)"}]


def test_codex_catalog_cache_never_reuses_another_workspace_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import account_models
    calls: list[Path]=[]
    async def read(profile: Path) -> tuple[list[dict[str,str]],str]:
        calls.append(profile)
        return [{"id":profile.name,"name":profile.name}],profile.name
    monkeypatch.setattr(account_models,"read_codex_models",read)
    async def check() -> None:
        cache=account_models.AccountModels()
        a,b=tmp_path/"workspace-a",tmp_path/"workspace-b"
        assert (await cache.codex(a))[1]=="workspace-a"
        assert (await cache.codex(a))[1]=="workspace-a"
        assert (await cache.codex(b))[1]=="workspace-b"
        assert calls==[a,b]
    asyncio.run(check())
