from piscinow.agent.handlers.base import ConversationHandler, FieldSpec
from piscinow.models.member import ProfileType


class CompradorHandler(ConversationHandler):
    profile_type = ProfileType.COMPRADOR
    role_description = "comprador que quer construir uma piscina"
    required_fields = [
        FieldSpec("name", "pergunte o nome completo do visitante"),
        FieldSpec("contact", "pergunte um telefone ou e-mail para contato"),
        FieldSpec("region", "pergunte em qual cidade/regiao sera a obra"),
        FieldSpec("intent", "pergunte que tipo de piscina e tamanho aproximado ele quer"),
    ]
