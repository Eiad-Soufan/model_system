from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings

class CustomUser(AbstractUser):
    ROLE_CHOICES = [
        ('manager', 'Management'),
        ('hr', 'HR'),
        ('employee', 'Employee'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='employee')

    # === الجديد ===
    points = models.IntegerField(default=0)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)

    def __str__(self):
        return self.username


class Section(models.Model):
    name_ar = models.CharField(max_length=100)
    name_en = models.CharField(max_length=100)

    def __str__(self):
        return self.name_ar

class FormModel(models.Model):
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='forms')
    serial_number = models.CharField(max_length=20, unique=True)
    name_ar = models.CharField(max_length=100)
    name_en = models.CharField(max_length=100)
    category = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to='forms/') 

    def __str__(self):
        return f"{self.name_ar} ({self.serial_number})"

class UserSectionPermission(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    section = models.ForeignKey(Section, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('user', 'section')


class Notification(models.Model):
    IMPORTANCE_CHOICES = [
        ('normal', 'عادي'),
        ('important', 'هام'),
    ]
    title = models.CharField(max_length=255)
    message = models.TextField()
    importance = models.CharField(max_length=10, choices=IMPORTANCE_CHOICES, default='normal')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class UserNotification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE)
    is_read = models.BooleanField(default=False)

    class Meta:
        unique_together = ('user', 'notification')


from django.contrib.auth import get_user_model
User = get_user_model()
class Complaint(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_complaints')
    recipient_type = models.CharField(
        max_length=10,
        choices=[('hr', 'HR'), ('manager', 'Manager')]
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    
    # ✅ الحقول الخاصة بالرد
    response = models.TextField(blank=True, null=True)
    is_responded = models.BooleanField(default=False)
    responded_at = models.DateTimeField(null=True, blank=True)
    responded_by = models.ForeignKey(  # ✅ من الذي رد
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='responded_complaints'
    )
    is_seen_by_employee = models.BooleanField(default=False)
    is_seen_by_recipient = models.BooleanField(default=False)  # for manager or HR

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Complaint by {self.sender.username} to {self.recipient_type}"

# =================== [Tasks Feature] Models ===================
from django.conf import settings as _settings
from django.utils import timezone as _timezone

UserModelLabel = _settings.AUTH_USER_MODEL

class TaskCreatorRole(models.TextChoices):
    MANAGEMENT = "management", "Management"
    HR = "hr", "Human Resources"

class TaskStatus(models.TextChoices):
    OPEN = "open", "Open"
    SUCCESS = "success", "Completed Successfully"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"

class TaskPhaseStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SUCCESS = "success", "Success"
    FAILED = "failed", "Failed"

class Task(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    creator_role = models.CharField(max_length=32, choices=TaskCreatorRole.choices)
    created_by = models.ForeignKey(UserModelLabel, on_delete=models.CASCADE, related_name="created_tasks")
    status = models.CharField(max_length=16, choices=TaskStatus.choices, default=TaskStatus.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def total_phases(self) -> int:
        return self.phases.count()

    @property
    def success_phases(self) -> int:
        return self.phases.filter(status=TaskPhaseStatus.SUCCESS).count()

    @property
    def progress_percent(self) -> float:
        total = self.total_phases
        return round((self.success_phases / total) * 100.0, 2) if total else 0.0

    def cancel(self, by_user):
        self.status = TaskStatus.CANCELLED
        self.updated_at = _timezone.now()
        self.save(update_fields=["status", "updated_at"])

    def mark_failed(self, by_user):
        self.status = TaskStatus.FAILED
        self.updated_at = _timezone.now()
        self.save(update_fields=["status", "updated_at"])

    def mark_success(self, by_user):
        self.status = TaskStatus.SUCCESS
        self.updated_at = _timezone.now()
        self.save(update_fields=["status", "updated_at"])

class TaskPhase(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="phases")
    order = models.PositiveIntegerField()
    text = models.TextField()
    status = models.CharField(max_length=16, choices=TaskPhaseStatus.choices, default=TaskPhaseStatus.PENDING)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("task", "order")
        ordering = ["order"]

    def complete(self, result: str):
        if result not in (TaskPhaseStatus.SUCCESS, TaskPhaseStatus.FAILED):
            raise ValueError("Invalid phase result")
        self.status = result
        self.completed_at = _timezone.now()
        self.save(update_fields=["status", "completed_at"])

class TaskRecipient(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="recipients")
    user = models.ForeignKey(UserModelLabel, on_delete=models.CASCADE, null=True, blank=True, related_name="assigned_tasks")
    is_hr_team = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(user__isnull=False, is_hr_team=False) |
                    models.Q(user__isnull=True, is_hr_team=True)
                ),
                name="recipient_is_user_xor_hrteam"
            )
        ]

class TaskComment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(UserModelLabel, on_delete=models.CASCADE, related_name="task_comments")
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


# ====================================
# =========================
# Surveys (استبيانات)
# =========================

class CreatorRole(models.TextChoices):
    MANAGER = "manager", "Manager"
    HR = "hr", "HR"

class SurveyStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"

class Survey(models.Model):
    """
    الاستبيان: عنوان + وصف + منشئ + دور المنشئ + حالة (نشر/مسودة/أرشيف)
    - يظهر للموظفين فقط عند PUBLISHED
    - في تبويب الإدارة: المدير يرى creator_role='manager'، والـ HR يرى creator_role='hr'
    """
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    creator = models.ForeignKey(
        _settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="surveys_created"
    )
    creator_role = models.CharField(
        max_length=16, choices=CreatorRole.choices, db_index=True
    )
    status = models.CharField(
        max_length=16, choices=SurveyStatus.choices, default=SurveyStatus.DRAFT, db_index=True
    )
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=_timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["creator_role", "status"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.status})"

    @property
    def is_published(self):
        return self.status == SurveyStatus.PUBLISHED

class SurveyQuestion(models.Model):
    """
    سؤال داخل الاستبيان
    """
    survey = models.ForeignKey(
        Survey, on_delete=models.CASCADE, related_name="questions"
    )
    text = models.CharField(max_length=1000)
    required = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        indexes = [
            models.Index(fields=["survey", "order"]),
        ]

    def __str__(self):
        return f"Q#{self.order} - {self.text[:40]}"

class SurveyOption(models.Model):
    """
    خيار لإجابة واحدة من السؤال (اختيار وحيد)
    """
    question = models.ForeignKey(
        SurveyQuestion, on_delete=models.CASCADE, related_name="options"
    )
    text = models.CharField(max_length=500)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        indexes = [
            models.Index(fields=["question", "order"]),
        ]

    def __str__(self):
        return self.text

class SurveySubmission(models.Model):
    """
    إرسال الموظف لاستبيان معيّن (مرّة واحدة لكل موظف/استبيان)
    """
    survey = models.ForeignKey(
        Survey, on_delete=models.CASCADE, related_name="submissions"
    )
    user = models.ForeignKey(
        _settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="survey_submissions"
    )
    created_at = models.DateTimeField(default=_timezone.now)

    class Meta:
        unique_together = [("survey", "user")]
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["survey", "user"]),
        ]

    def __str__(self):
        return f"Submission survey={self.survey_id} user={self.user_id}"

class SurveyAnswer(models.Model):
    """
    إجابة سؤال واحد ضمن الإرسال:
    - اختيار واحد فقط لكل سؤال (FK إلى SurveyOption)
    - نضمن عدم تكرار السؤال داخل نفس الإرسال
    """
    submission = models.ForeignKey(
        SurveySubmission, on_delete=models.CASCADE, related_name="answers"
    )
    question = models.ForeignKey(
        SurveyQuestion, on_delete=models.CASCADE, related_name="answers"
    )
    selected_option = models.ForeignKey(
        SurveyOption, on_delete=models.CASCADE, related_name="answers"
    )

    class Meta:
        unique_together = [("submission", "question")]
        indexes = [
            models.Index(fields=["question", "selected_option"]),
        ]

    def __str__(self):
        return f"Ans sub={self.submission_id} q={self.question_id} opt={self.selected_option_id}"


class EmployeePointLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='point_logs'
    )
    delta = models.IntegerField()  # موجب/سالب
    reason = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='point_changes_made'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} {self.delta:+} @ {self.created_at:%Y-%m-%d}"


from django.db import models
from django.utils.functional import cached_property

class HonorBoardSetting(models.Model):
    # نفترض Singleton عبر أول صف فقط
    enabled_month = models.BooleanField(default=True)
    enabled_year  = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Honor Board Setting"
        verbose_name_plural = "Honor Board Settings"

    @classmethod
    def get_singleton(cls):
        obj, _ = cls.objects.get_or_create(pk=1, defaults={})
        return obj

    # توافق للخلف: أي كود قديم كان يقرأ enabled
    @property
    def enabled(self):
        return self.enabled_month or self.enabled_year

    @enabled.setter
    def enabled(self, val: bool):
        # إبقاء نفس السلوك السابق عند ضبط enabled القديم
        self.enabled_month = bool(val)
        self.enabled_year  = bool(val)