"""Interactive configuration wizard for WildIdea CLI.

Usage:
    wildidea configure          # interactive setup
    wildidea configure --show   # show current config
    wildidea configure --reset  # reset to defaults
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional


CONFIG_DIR = Path.home() / ".wildidea"
CONFIG_FILE = CONFIG_DIR / "config.json"

PROVIDERS = {
    "1": {
        "name": "OpenRouter",
        "id": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "env_key": "OPENROUTER_API_KEY",
        "models": [
            "anthropic/claude-sonnet-4.5",
            "anthropic/claude-sonnet-4",
            "anthropic/claude-opus-4.8",
            "deepseek/deepseek-v4-pro",
            "deepseek/deepseek-r1",
            "google/gemini-2.5-flash",
            "openai/gpt-4.1",
        ],
    },
    "2": {
        "name": "OpenAI",
        "id": "openai",
        "base_url": "https://api.openai.com/v1",
        "env_key": "OPENAI_API_KEY",
        "models": [
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4o",
            "o3-mini",
        ],
    },
    "3": {
        "name": "Ollama (本地)",
        "id": "ollama",
        "base_url": "http://localhost:11434/v1",
        "env_key": None,
        "models": [
            "llama3.3:70b",
            "qwen2.5:72b",
            "deepseek-r1:70b",
            "mistral-large",
        ],
    },
    "4": {
        "name": "自定义 (OpenAI-compatible API)",
        "id": "custom",
        "base_url": None,
        "env_key": None,
        "models": [],
    },
}

JUDGE_MODELS = {
    "1": {"name": "Claude Sonnet 4.5 (推荐，论文原版)", "model": "anthropic/claude-sonnet-4.5"},
    "2": {"name": "DeepSeek V4 Pro (免费)", "model": "deepseek/deepseek-v4-pro"},
    "3": {"name": "和生成模型相同", "model": "same_as_generation"},
}


def load_config() -> dict:
    """Load config from ~/.wildidea/config.json."""
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


def save_config(config: dict):
    """Save config to ~/.wildidea/config.json."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False))
    print(f"\n配置已保存到 {CONFIG_FILE}")


def _select(options: dict[str, dict], prompt: str, display_key: str = "name") -> str:
    """Show a numbered selection menu and return the chosen key."""
    print(f"\n{prompt}")
    for key, val in options.items():
        print(f"  [{key}] {val[display_key]}")

    while True:
        choice = input("\n选择 (输入数字): ").strip()
        if choice in options:
            return choice
        print("无效选项，请重试")


def _input_secret(prompt: str) -> str:
    """Input a secret value (masks display)."""
    import getpass
    return getpass.getpass(f"{prompt}: ")


def _input_text(prompt: str, default: str = "") -> str:
    """Input text with optional default."""
    suffix = f" [{default}]" if default else ""
    val = input(f"{prompt}{suffix}: ").strip()
    return val if val else default


def configure():
    """Run the interactive configuration wizard."""
    print("=" * 50)
    print("WildIdea 配置向导")
    print("=" * 50)

    existing = load_config()

    # Step 1: Provider
    provider_key = _select(PROVIDERS, "选择 LLM 提供商:")
    provider = PROVIDERS[provider_key]

    # Step 2: API Key (if needed)
    api_key = None
    if provider["env_key"]:
        # Check if already in env
        env_val = os.environ.get(provider["env_key"], "")
        if env_val:
            print(f"\n已检测到环境变量 {provider['env_key']}={env_val[:8]}...{env_val[-4:]}")
            use_env = input("使用环境变量中的 key? (Y/n): ").strip().lower()
            if use_env != "n":
                api_key = "__ENV__"
            else:
                api_key = _input_secret(f"输入 {provider['name']} API Key")
        else:
            api_key = _input_secret(f"输入 {provider['name']} API Key")

    # Step 3: Base URL (custom only)
    base_url = provider["base_url"]
    if provider_key == "4":
        base_url = _input_text("输入 API Base URL", "http://localhost:8080/v1")

    # Step 4: Proxy
    existing_proxy = existing.get("proxy", "")
    default_proxy = existing_proxy or "http://127.0.0.1:7897"
    use_proxy = input(f"\n需要代理? (Y/n): ").strip().lower()
    proxy = ""
    if use_proxy != "n":
        proxy = _input_text("代理地址", default_proxy)

    # Step 5: Generation model
    if provider["models"]:
        models = {str(i + 1): {"name": m} for i, m in enumerate(provider["models"])}
        model_key = _select(models, "选择生成模型:")
        model = provider["models"][int(model_key) - 1]
    else:
        model = _input_text("输入模型名称")

    # Step 6: Judge model
    judge_key = _select(JUDGE_MODELS, "选择判官模型:")
    judge_model = JUDGE_MODELS[judge_key]["model"]

    # Save
    config = {
        "provider": provider["id"],
        "model": model,
        "judge_model": judge_model,
        "base_url": base_url,
        "proxy": proxy,
    }
    if api_key and api_key != "__ENV__":
        config["api_key"] = api_key

    save_config(config)

    # Summary
    print(f"\n{'='*50}")
    print(f"配置摘要:")
    print(f"  提供商: {provider['name']}")
    print(f"  模型:   {model}")
    print(f"  判官:   {judge_model}")
    print(f"  代理:   {proxy or '无'}")
    print(f"{'='*50}")
    print(f"\n现在可以直接跑了:")
    print(f"  wildidea generate \"你的问题\"")


def show_config():
    """Show current configuration."""
    config = load_config()
    if not config:
        print("未配置。运行 `wildidea configure` 进行设置。")
        return

    print(f"配置文件: {CONFIG_FILE}")
    print(f"{'='*40}")
    for k, v in config.items():
        if k == "api_key":
            print(f"  {k}: {v[:8]}...{v[-4:]}")
        else:
            print(f"  {k}: {v}")


def reset_config():
    """Reset configuration."""
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()
        print("配置已重置。")
    else:
        print("没有配置文件。")


def get_config() -> dict:
    """Get merged config: file defaults + env overrides + CLI args."""
    config = load_config()

    # Env overrides
    for provider_info in PROVIDERS.values():
        if provider_info["env_key"]:
            val = os.environ.get(provider_info["env_key"])
            if val:
                config.setdefault("api_key", val)
                break

    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if proxy:
        config.setdefault("proxy", proxy)

    return config


def main():
    import argparse
    parser = argparse.ArgumentParser(prog="wildidea-configure")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    if args.show:
        show_config()
    elif args.reset:
        reset_config()
    else:
        configure()


if __name__ == "__main__":
    main()
