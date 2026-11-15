"""Controller (C do MVC): recebe a requisição HTTP, confere login e permissão, chama o model e devolve JSON.

Cada módulo é um Blueprint do Flask com as rotas de um assunto; o Espiada.py junta todos.
Regra de negócio e SQL não ficam aqui: ficam nos models.
"""
