"""AI 调用客户端"""
import json
import requests
from utils.crypto import decrypt_password


class AIClient:
    def __init__(self, config):
        self.provider = config.provider
        self.endpoint = config.api_endpoint
        self.key = decrypt_password(config.api_key_encrypted) if config.api_key_encrypted else ''
        self.model = config.model_name
        self.temperature = config.temperature or 0.7
        self.max_tokens = config.max_tokens or 2048

    def test_connection(self):
        try:
            if self.provider == 'OpenAI':
                resp = requests.post(
                    self.endpoint or 'https://api.openai.com/v1/chat/completions',
                    headers={'Authorization': f'Bearer {self.key}', 'Content-Type': 'application/json'},
                    json={'model': self.model or 'gpt-4', 'messages': [{'role': 'user', 'content': 'Hello'}], 'max_tokens': 10},
                    timeout=15
                )
                return resp.status_code == 200, resp.text[:200]
            elif self.provider == 'Anthropic':
                resp = requests.post(
                    self.endpoint or 'https://api.anthropic.com/v1/messages',
                    headers={'x-api-key': self.key, 'Content-Type': 'application/json', 'anthropic-version': '2023-06-01'},
                    json={'model': self.model or 'claude-3-haiku-20240307', 'messages': [{'role': 'user', 'content': 'Hello'}], 'max_tokens': 10},
                    timeout=15
                )
                return resp.status_code == 200, resp.text[:200]
            elif self.provider == 'Ollama':
                resp = requests.post(
                    self.endpoint or 'http://localhost:11434/api/generate',
                    json={'model': self.model or 'llama3', 'prompt': 'Hello', 'stream': False},
                    timeout=15
                )
                return resp.status_code == 200, resp.text[:200]
            else:
                resp = requests.post(self.endpoint, json={'prompt': 'Hello', 'max_tokens': 10}, timeout=15)
                return resp.status_code == 200, resp.text[:200]
        except Exception as e:
            return False, str(e)

    def chat(self, prompt_text):
        """通用对话"""
        try:
            if self.provider == 'OpenAI':
                resp = requests.post(
                    self.endpoint or 'https://api.openai.com/v1/chat/completions',
                    headers={'Authorization': f'Bearer {self.key}', 'Content-Type': 'application/json'},
                    json={'model': self.model or 'gpt-4', 'messages': [{'role': 'user', 'content': prompt_text}],
                          'max_tokens': self.max_tokens, 'temperature': self.temperature},
                    timeout=60
                )
                data = resp.json()
                return data['choices'][0]['message']['content'] if data.get('choices') else resp.text
            elif self.provider == 'Anthropic':
                resp = requests.post(
                    self.endpoint or 'https://api.anthropic.com/v1/messages',
                    headers={'x-api-key': self.key, 'Content-Type': 'application/json', 'anthropic-version': '2023-06-01'},
                    json={'model': self.model or 'claude-3-haiku-20240307', 'messages': [{'role': 'user', 'content': prompt_text}],
                          'max_tokens': self.max_tokens},
                    timeout=60
                )
                data = resp.json()
                return data['content'][0]['text'] if data.get('content') else resp.text
            elif self.provider == 'Ollama':
                resp = requests.post(
                    self.endpoint or 'http://localhost:11434/api/generate',
                    json={'model': self.model or 'llama3', 'prompt': prompt_text, 'stream': False},
                    timeout=60
                )
                return resp.json().get('response', resp.text)
            else:
                resp = requests.post(self.endpoint, json={'prompt': prompt_text, 'max_tokens': self.max_tokens}, timeout=60)
                return resp.text[:2000]
        except Exception as e:
            return f'[AI Error] {e}'

    def analyze_inspection(self, device_info, metrics, history):
        prompt = f"请分析以下设备的巡检指标并给出诊断建议：\n设备信息：{device_info}\n当前指标：{metrics}\n历史趋势：{history}"
        return self.chat(prompt)

    def analyze_fault(self, ticket_info, device_info, logs):
        prompt = f"请分析以下故障并给出诊断和解决方案：\n工单信息：{ticket_info}\n设备信息：{device_info}\n日志：{logs}"
        return self.chat(prompt)
