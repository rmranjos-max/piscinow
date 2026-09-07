from piscinow.agent.handlers.base import ConversationHandler, FieldSpec
from piscinow.models.member import ProfileType


class PrestadorHandler(ConversationHandler):
    profile_type = ProfileType.PRESTADOR
    role_description = "prestador de servico que quer se cadastrar como instalador"
    required_fields = [
        FieldSpec("name", "pergunte o nome do prestador ou da empresa"),
        FieldSpec("contact", "pergunte um telefone ou e-mail para contato"),
        FieldSpec("document", "pergunte o CPF ou CNPJ"),
        FieldSpec("region", "pergunte em quais cidades/regioes ele atende"),
        FieldSpec("experience_years", "pergunte ha quantos anos trabalha com obras de piscina"),
    ]
