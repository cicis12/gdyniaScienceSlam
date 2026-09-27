from enum import Enum 
from typing import List, Optional, Any, Dict, Literal
from pydantic import BaseModel, EmailStr, Field, field_validator, create_model

class FieldType(str, Enum):
    TEXT = "text"
    EMAIL = "email"
    PHONE = "phone"
    DOUBLE = "double"
    TEXTAREA = "textarea"
    SCHOOL = "school"
    FILE = "file"
    INFOTEXT_LARGE = "infotext_large"
    INFOTEXT_MEDIUM = "infotext_medium"
    INFOTEXT_SMALL = "infotext_small"
    INFOTEXT_PARAGRAPH = "infotext_paragraph"
    LIST_CHOICE = "list_choice"
    CHECKBOX = "checkbox"

class FormField(BaseModel):
    name: str
    name2: Optional[str] = None
    type: FieldType
    question: str
    question2: Optional[str] = None
    svg: Optional[str] = None
    note: Optional[str] = None
    required: bool = False
    options: Optional[List[str]] = None

    @property
    def is_input(self) -> bool:
        return not self.type.value.startswith("infotext_")

class FormDefinition(BaseModel):
    fields: List[FormField]

class FormPayload(BaseModel):
    form_id: int
    form_version_id: int
    answers: Dict[str, Any]

def build_submission_model(definition: FormDefinition) -> type[BaseModel]:
    fields_spec = {}

    for f in definition.fields:
        if not f.is_input:
            continue
        
        py_type: Any = str
        if f.type == FieldType.EMAIL:
            py_type = EmailStr
        elif f.type == FieldType.LIST_CHOICE:
            if f.options:
                py_type = Literal[tuple(f.options)]
            else:
                py_type = str
            
        default = ... if f.required else None
        fields_spec[f.name] = (Optional[py_type] if not f.required else py_type, default)

        if f.type == FieldType.DOUBLE:
            fields_spec[f.name2] = (Optional[py_type] if not f.required else py_type, default)

    return create_model("DynamicSubmission", __config__={"extra": "forbid"}, **fields_spec)