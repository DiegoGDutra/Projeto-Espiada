"""Model (M do MVC): dados e regras de negócio.

Cada módulo cuida de um assunto do banco. Nenhum deles conhece HTTP, sessão ou tela:
recebem valores comuns (str, dict) e devolvem dicts. Erro de regra vira ErroModelo,
que o app traduz para a resposta JSON certa.
"""
