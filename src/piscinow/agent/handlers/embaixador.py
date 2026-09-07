from piscinow.agent.handlers.base import ConversationHandler, FieldSpec
from piscinow.models.member import ProfileType


class EmbaixadorHandler(ConversationHandler):
    profile_type = ProfileType.EMBAIXADOR
    role_description = "pessoa que quer se tornar embaixador do Clube e indicar amigos"
    required_fields = [
        FieldSpec("name", "pergunte o nome completo"),
        FieldSpec("contact", "pergunte um telefone ou e-mail para contato"),
    ]
