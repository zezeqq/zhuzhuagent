from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Generator

import httpx


class ModelClientError(RuntimeError):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResponse:
    tool_calls: list[ToolCall] = field(default_factory=list)
    content: str | None = None
    raw_message: dict = field(default_factory=dict)


class ModelClient:
    _http: httpx.Client | None = None

    @classmethod
    def _client(cls) -> httpx.Client:
        if cls._http is None:
            cls._http = httpx.Client(timeout=120, limits=httpx.Limits(max_connections=20))
        return cls._http

    def chat(self, messages: list[dict], model_config: dict, temperature=None, max_tokens=None) -> str:
        api_key, api_base, model_name = self._validate(model_config)
        payload = self._payload(messages, model_name, model_config, temperature, max_tokens, stream=False)
        headers = self._headers(api_key)
        try:
            resp = self._client().post(f"{api_base}/chat/completions", headers=headers, json=payload)
            if resp.status_code != 200:
                try:
                    detail = resp.json().get("error", {}).get("message", resp.text[:500])
                except Exception:
                    detail = resp.text[:500]
                raise ModelClientError(f"模型 [{model_name}] 调用失败（{resp.status_code}）：{detail}")
            return resp.json()["choices"][0]["message"]["content"]
        except ModelClientError:
            raise
        except Exception as exc:
            raise ModelClientError(f"模型调用失败：{exc}") from exc

    def chat_with_tools(
        self,
        messages: list[dict],
        model_config: dict,
        tools: list[dict] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ToolResponse:
        api_key, api_base, model_name = self._validate(model_config)
        payload = self._payload(messages, model_name, model_config, temperature, max_tokens, stream=False)
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
            payload["parallel_tool_calls"] = True
        headers = self._headers(api_key)
        try:
            resp = self._client().post(f"{api_base}/chat/completions", headers=headers, json=payload)
            if resp.status_code != 200:
                try:
                    detail = resp.json().get("error", {}).get("message", resp.text[:500])
                except Exception:
                    detail = resp.text[:500]
                raise ModelClientError(
                    f"模型 [{model_name}] 调用失败（{resp.status_code}）：{detail}"
                )
            data = resp.json()
            choice = data["choices"][0]
            message = choice["message"]

            tool_calls_raw = message.get("tool_calls") or []
            tool_calls = []
            for tc in tool_calls_raw:
                func = tc.get("function", {})
                args_str = func.get("arguments", "{}")
                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                except json.JSONDecodeError:
                    args = {"raw": args_str}
                tool_calls.append(ToolCall(
                    id=tc.get("id", ""),
                    name=func.get("name", ""),
                    arguments=args,
                ))

            content = message.get("content")
            return ToolResponse(
                tool_calls=tool_calls,
                content=content,
                raw_message=message,
            )
        except ModelClientError:
            raise
        except Exception as exc:
            raise ModelClientError(f"工具调用失败：{exc}") from exc

    def stream_chat(self, messages: list[dict], model_config: dict, temperature=None, max_tokens=None) -> Generator[str, None, None]:
        api_key, api_base, model_name = self._validate(model_config)
        payload = self._payload(messages, model_name, model_config, temperature, max_tokens, stream=True)
        headers = self._headers(api_key)
        try:
            with httpx.Client(timeout=300) as client:
                with client.stream("POST", f"{api_base}/chat/completions", headers=headers, json=payload) as resp:
                    resp.raise_for_status()
                    for line in resp.iter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            chunk = delta.get("content", "")
                            if chunk:
                                yield chunk
                        except (json.JSONDecodeError, IndexError, KeyError):
                            continue
        except Exception as exc:
            raise ModelClientError(f"流式调用失败：{exc}") from exc

    def transcribe_audio(self, audio_path: str, model_config: dict, transcription_model: str = "whisper-1") -> str:
        """Transcribe a local audio file through an OpenAI-compatible audio endpoint."""
        api_key, api_base, _ = self._validate(model_config)
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            with open(audio_path, "rb") as audio:
                files = {"file": (audio_path.split("\\")[-1], audio, "audio/wav")}
                data = {"model": transcription_model}
                resp = self._client().post(
                    f"{api_base}/audio/transcriptions",
                    headers=headers,
                    data=data,
                    files=files,
                    timeout=180,
                )
            if resp.status_code != 200:
                try:
                    detail = resp.json().get("error", {}).get("message", resp.text[:500])
                except Exception:
                    detail = resp.text[:500]
                raise ModelClientError(f"语音转写失败（{resp.status_code}）：{detail}")
            payload = resp.json()
            return (payload.get("text") or "").strip()
        except ModelClientError:
            raise
        except Exception as exc:
            raise ModelClientError(f"语音转写失败：{exc}") from exc

    @staticmethod
    def normalize_api_base(api_base: str) -> str:
        """Fix common API Base mistakes (e.g. Moonshot missing /v1)."""
        import re

        base = (api_base or "").strip().rstrip("/")
        if not base:
            return base

        lower = base.lower()
        if re.search(r"/v\d+(?:/|$)", lower):
            return base

        needs_v1 = (
            "moonshot.cn" in lower,
            "openai.com" in lower,
            "hunyuan.cloud.tencent.com" in lower,
            "localhost:11434" in lower,
        )
        if any(needs_v1):
            return f"{base}/v1"
        return base

    @staticmethod
    def _validate(model_config: dict) -> tuple[str, str, str]:
        cfg = model_config or {}
        api_key = cfg.get("api_key") or ""
        api_base = ModelClient.normalize_api_base(cfg.get("api_base") or "")
        model_name = cfg.get("model_name") or ""
        if not api_base:
            raise ModelClientError("当前模型没有配置 API Base，请在模型管理中填写。")
        if not api_key:
            raise ModelClientError("当前模型没有配置 API Key。请在模型管理中填写密钥后再调用。")
        if not model_name:
            raise ModelClientError("当前模型没有配置 model_name。")
        return api_key, api_base, model_name

    @staticmethod
    def _headers(api_key: str) -> dict:
        return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    @staticmethod
    def _resolve_temperature(model_name: str, temperature, model_config) -> float:
        if temperature is not None:
            resolved = float(temperature)
        else:
            resolved = float(model_config.get("temperature", 0.7))

        lower = (model_name or "").lower()
        if "kimi-k2" in lower or "k2.7" in lower:
            return 1.0
        return resolved

    @staticmethod
    def _payload(messages, model_name, model_config, temperature, max_tokens, stream) -> dict:
        from core.model_profiles import is_deepseek_v4

        cfg = model_config or {}
        payload: dict = {
            "model": model_name,
            "messages": messages,
            "stream": stream,
        }
        if is_deepseek_v4(cfg):
            if cfg.get("thinking_enabled", 1):
                payload["thinking"] = {"type": "enabled"}
            effort = (cfg.get("reasoning_effort") or "max").strip()
            if effort:
                payload["reasoning_effort"] = effort
        else:
            payload["temperature"] = ModelClient._resolve_temperature(
                model_name, temperature, model_config,
            )
        resolved_max = max_tokens if max_tokens is not None else cfg.get("max_tokens")
        if resolved_max and int(resolved_max) > 0:
            payload["max_tokens"] = int(resolved_max)
        return payload


def chat(messages, model_config, temperature=None, max_tokens=None):
    return ModelClient().chat(messages, model_config, temperature, max_tokens)
