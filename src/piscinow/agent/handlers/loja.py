from piscinow.agent.handlers.base import ConversationHandler, FieldSpec
from piscinow.models.member import ProfileType


class LojaHandler(ConversationHandler):
    profile_type = ProfileType.LOJA
    role_description = "loja que quer se cadastrar como fornecedora"
    required_fields = [
        FieldSpec("name", "pergunte o nome da loja"),
        FieldSpec("contact", "pergunte um telefone ou e-mail para contato"),
        FieldSpec("cnpj", "pergunte o CNPJ da loja"),
        FieldSpec("region", "pergunte em qual cidade/regiao a loja atende"),
        FieldSpec(
            "categories",
            "pergunte quais categorias de produto a loja trabalha (vinil, fibra, alvenaria, equipamentos)",
        ),
    ]
