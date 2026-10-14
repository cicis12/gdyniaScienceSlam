from enum import Enum 
from typing import List, Optional, Any, Dict, Literal, Annotated
from pydantic import BaseModel, EmailStr, Field, field_validator, create_model, BeforeValidator
from file_types import DEFAULT_FILE_CATEGORIES

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

def empty_to_none(value):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return value


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
    accepted_types: List[Literal['videos', 'images', 'documents', 'archives']] = Field(
        default_factory=lambda: list(DEFAULT_FILE_CATEGORIES), min_length=1, max_length=4)

    @field_validator('svg', mode='before')
    @classmethod
    def normalize_svg(cls, value):
        return empty_to_none(value)

    @property
    def is_input(self) -> bool:
        return not self.type.value.startswith("infotext_")

class FormDefinition(BaseModel):
    svg: Optional[str] = None

    @field_validator('svg', mode='before')
    @classmethod
    def normalize_svg(cls, value):
        return empty_to_none(value)

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
        
        py_type: Any = Annotated[str, Field(max_length=10000)]
        if f.type == FieldType.EMAIL:
            py_type = EmailStr
        elif f.type == FieldType.LIST_CHOICE:
            if f.options:
                py_type = Literal[tuple(f.options)]
            else:
                py_type = Annotated[str, Field(max_length=10000)]
            
        if f.type == FieldType.CHECKBOX:
            py_type = Literal['true'] if f.required else Literal['true', 'false']
        elif f.required and f.type != FieldType.EMAIL and (f.type != FieldType.LIST_CHOICE or not f.options):
            py_type = Annotated[str, Field(min_length=1, max_length=10000)]

        if not f.required:
            py_type = Annotated[Optional[py_type], BeforeValidator(empty_to_none)]
        default = ... if f.required else None
        fields_spec[f.name] = (py_type, default)

        if f.type == FieldType.DOUBLE:
            fields_spec[f.name2] = (py_type, default)

    return create_model("DynamicSubmission", __config__={"extra": "forbid"}, **fields_spec)
