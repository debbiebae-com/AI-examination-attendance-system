from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    programme: Mapped[str] = mapped_column(String(120))
    level: Mapped[int] = mapped_column(Integer)
    fees_cleared: Mapped[bool] = mapped_column(Boolean, default=True)
    suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    # Enrollment photo, relative to backend/. Null if no reference photo exists.
    photo_path: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Exam(Base):
    __tablename__ = "exams"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_code: Mapped[str] = mapped_column(String(16), index=True)
    course_title: Mapped[str] = mapped_column(String(120))
    hall: Mapped[str] = mapped_column(String(64))
    starts_at: Mapped[datetime] = mapped_column(DateTime)
    ends_at: Mapped[datetime] = mapped_column(DateTime)


class Registration(Base):
    """A student is registered for an exam (course enrollment)."""

    __tablename__ = "registrations"
    __table_args__ = (UniqueConstraint("student_id", "exam_id", name="uq_registration"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id"))


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    # Database-level guarantee: one attendance record per student per exam.
    __table_args__ = (UniqueConstraint("exam_id", "student_id", name="uq_attendance_exam_student"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime)  # stored as UTC; Ghana is UTC+0
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="manual")  # "camera" or "manual"

    student: Mapped[Student] = relationship()


class FaceEmbedding(Base):
    """A 512-d ArcFace embedding stored as float32 bytes, one row per enrollment photo."""

    __tablename__ = "face_embeddings"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    embedding: Mapped[bytes] = mapped_column(LargeBinary)
    source_photo: Mapped[str] = mapped_column(String(255))
    det_score: Mapped[float] = mapped_column(Float)
