from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TranscriptForm(BaseModel):
    text: str = Field(..., min_length=10, description="课堂转写文本")
    duration_sec: float = Field(2700, gt=0, description="课堂时长（秒），默认 45 分钟")
    reference: str | None = Field(
        None,
        description="课程大纲（选填）。有则对照大纲安排评本节课完整性，没有则根据转写评闭环",
    )


class EvaluationTaskCreateForm(BaseModel):
    filename: str = Field(..., min_length=1, max_length=512)

    @field_validator("filename")
    @classmethod
    def strip_filename(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("文件名不能为空")
        return text


class RemoteSourceForm(BaseModel):
    url: str = Field(..., min_length=1, max_length=8192)
    password: str = Field("", max_length=128)
    path: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value):
        if any(not item or len(item) > 2048 for item in value):
            raise ValueError("无效的网盘目录路径")
        return value


class UploadSessionCreateForm(BaseModel):
    mode: str = Field(..., pattern="^(original|evidence)$")
    fingerprint: str = Field(..., min_length=64, max_length=64)
    original_filename: str = Field(..., min_length=1, max_length=512)
    original_size: int = Field(..., gt=0, le=20 * 1024 * 1024 * 1024)
    audio_filename: str | None = Field(None, max_length=512)
    audio_mime: str | None = Field(None, max_length=128)


class UploadSessionCompleteForm(BaseModel):
    session_id: str = Field(..., min_length=16, max_length=128)
    audio_parts: int | None = Field(None, gt=0, le=100_000)
    frame_parts: int | None = Field(None, gt=0, le=100_000)
    manifest: dict | None = None


class QAForm(BaseModel):
    question: str = Field(..., min_length=1)
    mode: Literal[
        "ask", "syllabus_design", "teaching_design", "learning_diagnosis"
    ] = Field("ask", description="问答工作模式")
    session_id: str | None = None
    corpora: list[str] | None = Field(
        None, description="限定检索的语料库；省略则使用模式默认库，空列表则不检索"
    )
    eval_task_ids: list[str] | None = Field(
        None,
        description=(
            "限定检索的评估任务，只作用于 eval_reports。"
            "省略则检索该用户全部已完成报告；空列表则不检索报告"
        ),
        max_length=200,
    )
    attachment_ids: list[str] | None = Field(
        None,
        description="本轮问答指定带入的私有上传材料 ID；不会写入公共知识库",
        max_length=12,
    )


class SessionPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=80)
    pinned: bool | None = None


class SyllabusTextForm(BaseModel):
    text: str = Field(..., min_length=10)
    prompt_mode: str | None = Field(
        None,
        description=(
            "adaptive（灵活 XML）| schema（固定 XML 框架）| "
            "markdown（灵活 Markdown）| markdown_schema（固定 Markdown 框架）；"
            "默认读 config.yaml"
        ),
    )


class RegisterForm(BaseModel):
    school: str = Field(..., min_length=1, max_length=80)
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=1, max_length=64)
    confirm_password: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=40)
    invite_code: str | None = Field(None, max_length=64)
    role: str | None = Field(None, description="忽略。注册不能指定角色")

    @field_validator("school", "username", "display_name")
    @classmethod
    def strip_text(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("不能为空")
        return text

    @field_validator("role")
    @classmethod
    def reject_role(cls, value: str | None) -> None:
        return None


class LoginForm(BaseModel):
    school: str = Field("", max_length=80)
    username: str = Field(..., min_length=1, max_length=32)
    password: str = Field(..., min_length=1, max_length=64)

    @field_validator("school")
    @classmethod
    def strip_school(cls, value: str | None) -> str:
        return (value or "").strip()

    @field_validator("username", "password")
    @classmethod
    def strip_text(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("不能为空")
        return text


class UserSettingsForm(BaseModel):
    settings: dict


class ChangePasswordForm(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=64)
    new_password: str = Field(..., min_length=1, max_length=64)
    confirm_password: str = Field(..., min_length=1, max_length=64)


class AdminRoleForm(BaseModel):
    role: str = Field(..., pattern="^(user|admin)$")


class AdminPasswordForm(BaseModel):
    password: str = Field(..., min_length=1, max_length=64)


class ProfileUpdateForm(BaseModel):
    name: str | None = Field(None, max_length=40)
    staff_id: str | None = Field(None, max_length=32)
    school: str | None = Field(None, max_length=80)
    department: str | None = Field(None, max_length=80)
    email: str | None = Field(None, max_length=80)
    phone: str | None = Field(None, max_length=20)
    title: str | None = Field(None, max_length=32)
    courses: str | None = Field(None, max_length=200)
    bio: str | None = Field(None, max_length=400)

    @field_validator("name", "staff_id", "school", "department", "email", "phone", "title", "courses", "bio")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()

    @field_validator("email")
    @classmethod
    def check_email(cls, value: str | None) -> str | None:
        if not value:
            return value
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("邮箱格式不正确")
        return value
