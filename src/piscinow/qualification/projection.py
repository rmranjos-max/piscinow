import hashlib
import uuid

from piscinow.qualification.fields import FIELDS, label_for


def partner_briefing(member_id: uuid.UUID, values: dict) -> dict:
    """What a partner store may see about a buyer: an anonymous code and the project facts.

    Built only from the field catalog, so a name, email or phone can never be added by accident.
    """
    code = hashlib.sha256(str(member_id).encode()).hexdigest()[:4].upper()
    fields = [
        {"rotulo": field.label, "valor": label_for(key, values[key])}
        for key, field in FIELDS.items()
        if isinstance(values.get(key), str) and values[key]
    ]
    return {"codigo": f"Cliente #{code}", "campos": fields}
