from rest_framework import serializers
from .models import Section, FormModel
from .models import Notification, UserNotification
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import Complaint
from .models import CustomUser, EmployeePointLog, HonorBoardSetting

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # نضيف معلومات إضافية داخل التوكن
        token['username'] = user.username
        token['is_staff'] = user.is_staff
        token['is_superuser'] = user.is_superuser
        # === إضافاتنا الخفيفة (لا تؤثر على القديم) ===
        token['role'] = getattr(user, 'role', 'employee')
        token['points'] = getattr(user, 'points', 0)
        token['avatar'] = (user.avatar.url if getattr(user, 'avatar', None) else None)
        
        return token
    
class SectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ['id', 'name_ar', 'name_en']

class FormModelSerializer(serializers.ModelSerializer):
    section = SectionSerializer(read_only=True)

    class Meta:
        model = FormModel
        fields = [
            'id', 'serial_number', 'name_ar', 'name_en',
            'category', 'description', 'file', 'section'
        ]


class NotificationSerializer(serializers.ModelSerializer):
    importance_display = serializers.CharField(source='get_importance_display', read_only=True)

    class Meta:
        model = Notification
        fields = ['id', 'title', 'message', 'importance', 'importance_display', 'created_at']

class UserNotificationSerializer(serializers.ModelSerializer):
    notification = NotificationSerializer()

    class Meta:
        model = UserNotification
        fields = ['id', 'notification', 'is_read']

class ComplaintSerializer(serializers.ModelSerializer):
    sender_username = serializers.CharField(source='sender.username', read_only=True)
    recipient_display = serializers.SerializerMethodField()
    is_seen_by_employee = serializers.BooleanField(read_only=True)
    is_seen_by_recipient = serializers.BooleanField(read_only=True)

    class Meta:
        model = Complaint
        fields = '__all__'
        read_only_fields = [
            'sender',
            'sender_username',
            'created_at',
            'is_responded',
            'response',
            'responded_at',
            'recipient_display'
        ]

    def get_recipient_display(self, obj):
        return obj.get_recipient_type_display()

# === [Tasks Feature] Serializers ===
from django.contrib.auth import get_user_model as _get_user_model
from rest_framework import serializers as _s
from .models import Task, TaskPhase, TaskRecipient, TaskComment, TaskStatus, TaskPhaseStatus

_User = _get_user_model()

def _infer_role(user):
    role = str(getattr(user, "role", "") or "").lower()
    if role in ("manager", "branch_manager", "general_manager"):
        return "manager" if role in ("manager", "branch_manager") else "general_manager"
    if role in ("hr", "human_resources"):
        return "hr"
    if getattr(user, "is_superuser", False):
        return "general_manager"
    if getattr(user, "is_staff", False):
        return "hr"
    return "employee"

class TaskPhaseSerializer(_s.ModelSerializer):
    class Meta:
        model = TaskPhase
        fields = ["id", "order", "text", "status", "completed_at"]
        read_only_fields = ["id", "completed_at"]

class TaskRecipientSerializer(_s.ModelSerializer):
    user_username = _s.CharField(source="user.username", read_only=True)
    user_full_name = _s.SerializerMethodField()

    class Meta:
        model = TaskRecipient
        fields = ["id", "user", "is_hr_team", "user_username", "user_full_name"]
        read_only_fields = ["id", "user_username", "user_full_name"]

    def get_user_full_name(self, obj):
        try:
            # يفضل الاسم الكامل، وإن لم يوجد يرجع فارغ
            name = obj.user.get_full_name()
            return name or ""
        except Exception:
            return ""

class TaskCommentSerializer(_s.ModelSerializer):
    author_name = _s.SerializerMethodField()

    class Meta:
        model = TaskComment
        fields = ["id", "author", "author_name", "text", "created_at"]
        read_only_fields = ["id", "author", "author_name", "created_at"]

    def get_author_name(self, obj):
        return getattr(obj.author, "get_full_name", lambda: obj.author.username)()

class TaskSerializer(_s.ModelSerializer):
    phases = TaskPhaseSerializer(many=True, read_only=True)
    recipients = TaskRecipientSerializer(many=True, read_only=True)
    progress_percent = _s.FloatField(read_only=True)

    phase_texts = _s.ListField(child=_s.CharField(), write_only=True, required=False)
    recipient_user_ids = _s.ListField(child=_s.IntegerField(), write_only=True, required=False, default=[])
    to_hr_team = _s.BooleanField(write_only=True, required=False, default=False)

    class Meta:
            model = Task
            fields = [
                "id", "title", "description", "creator_role", "created_by", "status",
                "created_at", "updated_at", "phases", "recipients", "progress_percent",
                "phase_texts", "recipient_user_ids", "to_hr_team"
            ]
            read_only_fields = [
                "id",
                "created_by",
                "created_at",
                "updated_at",
                "phases",
                "recipients",
                "progress_percent",
                "creator_role",  # ← أضف هذا السطر
            ]

    def create(self, validated):
        request = self.context["request"]
        user = request.user
        role = _infer_role(user)
        creator_role = "management" if role in ("manager", "general_manager") else "hr"

        phase_texts = validated.pop("phase_texts", [])
        recipient_user_ids = validated.pop("recipient_user_ids", [])
        to_hr_team = validated.pop("to_hr_team", False)

        task = Task.objects.create(created_by=user, creator_role=creator_role, **validated)

        for idx, text in enumerate(phase_texts, start=1):
            TaskPhase.objects.create(task=task, order=idx, text=text)

        for uid in recipient_user_ids:
            TaskRecipient.objects.create(task=task, user_id=uid)
        if to_hr_team:
            TaskRecipient.objects.create(task=task, is_hr_team=True)

        return task

    def update(self, instance, validated):
        phase_texts = validated.pop("phase_texts", None)
        recipient_user_ids = validated.pop("recipient_user_ids", None)
        to_hr_team = validated.pop("to_hr_team", None)

        for k, v in validated.items():
            setattr(instance, k, v)
        instance.save()

        if phase_texts is not None:
            instance.phases.all().delete()
            for idx, text in enumerate(phase_texts, start=1):
                TaskPhase.objects.create(task=instance, order=idx, text=text)

        if (recipient_user_ids is not None) or (to_hr_team is not None):
            instance.recipients.all().delete()
            if recipient_user_ids:
                for uid in recipient_user_ids:
                    TaskRecipient.objects.create(task=instance, user_id=uid)
            if to_hr_team:
                TaskRecipient.objects.create(task=instance, is_hr_team=True)

        return instance



# ====================================
# =========================
# Surveys (استبيانات)
# =========================
from django.db import transaction
from django.utils import timezone as _timezone

from .models import (
    Survey, SurveyQuestion, SurveyOption,
    SurveySubmission, SurveyAnswer,
    SurveyStatus, CreatorRole,
)

class SurveyOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyOption
        fields = ["id", "text", "order"]
        read_only_fields = ["id"]


class SurveyQuestionSerializer(serializers.ModelSerializer):
    options = SurveyOptionSerializer(many=True, read_only=True)

    class Meta:
        model = SurveyQuestion
        fields = ["id", "text", "required", "order", "options"]
        read_only_fields = ["id", "options"]


class SurveySerializer(serializers.ModelSerializer):
    questions = SurveyQuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Survey
        fields = [
            "id", "title", "description",
            "creator", "creator_role",
            "status", "published_at",
            "created_at", "updated_at",
            "questions",
        ]
        read_only_fields = ["id", "creator", "creator_role", "published_at", "created_at", "updated_at", "questions"]


class SurveyOptionWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyOption
        fields = ["id", "text", "order"]
        read_only_fields = ["id"]


class SurveyQuestionWriteSerializer(serializers.ModelSerializer):
    options = SurveyOptionWriteSerializer(many=True)

    class Meta:
        model = SurveyQuestion
        fields = ["id", "text", "required", "order", "options"]
        read_only_fields = ["id"]

    def validate(self, data):
        opts = data.get("options") or []
        if not opts:
            raise serializers.ValidationError("Question must include at least one option.")
        return data


class SurveyWriteSerializer(serializers.ModelSerializer):
    questions = SurveyQuestionWriteSerializer(many=True)

    class Meta:
        model = Survey
        fields = [
            "id", "title", "description",
            "status",     # draft/published/archived
            "questions",
        ]
        read_only_fields = ["id"]

    def _get_role_from_request(self):
        request = self.context.get("request")
        role = ""
        if request and getattr(request, "user", None):
            role = (getattr(request.user, "role", "") or "").lower()
        # يمكن تمرير الدور من الفيو عبر context إذا أردت فرضه صراحة
        role_ctx = (self.context.get("creator_role") or "").lower()
        return role_ctx or role or None

    @transaction.atomic
    def create(self, validated):
        questions = validated.pop("questions", [])
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None

        survey = Survey.objects.create(
            title=validated.get("title"),
            description=(validated.get("description") or ""),
            creator=user,
            creator_role=(self._get_role_from_request() or CreatorRole.MANAGER),
            status=validated.get("status") or SurveyStatus.DRAFT,
            published_at=_timezone.now() if validated.get("status") == SurveyStatus.PUBLISHED else None,
        )

        for i, qd in enumerate(questions):
            q = SurveyQuestion.objects.create(
                survey=survey,
                text=qd["text"],
                required=qd.get("required", True),
                order=qd.get("order", i),
            )
            for j, od in enumerate(qd.get("options", [])):
                SurveyOption.objects.create(
                    question=q,
                    text=od["text"],
                    order=od.get("order", j),
                )
        return survey

    @transaction.atomic
    def update(self, instance: Survey, validated):
        status_before = instance.status
        instance.title = validated.get("title", instance.title)
        instance.description = validated.get("description", instance.description)
        new_status = validated.get("status", instance.status)

        if status_before != SurveyStatus.PUBLISHED and new_status == SurveyStatus.PUBLISHED:
            instance.published_at = _timezone.now()
        instance.status = new_status
        instance.save()

        if "questions" in validated:
            instance.questions.all().delete()
            questions = validated.get("questions") or []
            for i, qd in enumerate(questions):
                q = SurveyQuestion.objects.create(
                    survey=instance,
                    text=qd["text"],
                    required=qd.get("required", True),
                    order=qd.get("order", i),
                )
                for j, od in enumerate(qd.get("options", [])):
                    SurveyOption.objects.create(
                        question=q,
                        text=od["text"],
                        order=od.get("order", j),
                    )
        return instance


class SurveyAnswerWriteItem(serializers.Serializer):
    question = serializers.IntegerField()
    selected_option = serializers.IntegerField()

    def validate(self, data):
        try:
            q = SurveyQuestion.objects.get(id=data["question"])
        except SurveyQuestion.DoesNotExist:
            raise serializers.ValidationError("Invalid question.")

        try:
            opt = SurveyOption.objects.get(id=data["selected_option"])
        except SurveyOption.DoesNotExist:
            raise serializers.ValidationError("Invalid option.")

        if opt.question_id != q.id:
            raise serializers.ValidationError("Option does not belong to the given question.")

        # نخزّن الكائنات لاستخدامها في create
        data["_question_obj"] = q
        data["_option_obj"] = opt
        return data


class SurveySubmissionWriteSerializer(serializers.ModelSerializer):
    answers = SurveyAnswerWriteItem(many=True)

    class Meta:
        model = SurveySubmission
        fields = ["id", "survey", "answers", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate(self, data):
        survey = data.get("survey")
        if not survey:
            raise serializers.ValidationError("Survey is required.")
        if survey.status != SurveyStatus.PUBLISHED:
            raise serializers.ValidationError("Survey is not published.")

        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        if not user or not user.is_authenticated:
            raise serializers.ValidationError("Authentication required.")

        if SurveySubmission.objects.filter(survey=survey, user=user).exists():
            raise serializers.ValidationError("You have already submitted this survey.")
        return data

    @transaction.atomic
    def create(self, validated):
        answers = validated.pop("answers", [])
        survey = validated["survey"]
        request = self.context.get("request")
        user = getattr(request, "user", None)

        # جميع الأسئلة required يجب أن تُجاب
        required_q_ids = list(survey.questions.filter(required=True).values_list("id", flat=True))
        answered_q_ids = set()
        for item in answers:
            q = item.get("_question_obj")
            if not q or q.survey_id != survey.id:
                raise serializers.ValidationError("Question does not belong to this survey.")
            answered_q_ids.add(q.id)
        missing = [qid for qid in required_q_ids if qid not in answered_q_ids]
        if missing:
            raise serializers.ValidationError("Please answer all required questions.")

        sub = SurveySubmission.objects.create(survey=survey, user=user)
        for item in answers:
            SurveyAnswer.objects.create(
                submission=sub,
                question=item["_question_obj"],
                selected_option=item["_option_obj"],
            )
        return sub



class SurveyOptionResultSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    text = serializers.CharField()
    count = serializers.IntegerField()
    percentage = serializers.FloatField()


class SurveyQuestionResultSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    text = serializers.CharField()
    required = serializers.BooleanField()
    options = SurveyOptionResultSerializer(many=True)


class SurveyResultsSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    description = serializers.CharField()
    status = serializers.CharField()
    creator_role = serializers.CharField()
    total_submissions = serializers.IntegerField()
    questions = SurveyQuestionResultSerializer(many=True)

    def to_representation(self, survey: Survey):
        total_sub = survey.submissions.count()
        q_blocks = []
        for q in survey.questions.all().order_by("order", "id"):
            opts = []
            for opt in q.options.all().order_by("order", "id"):
                c = opt.answers.count()
                pct = (c * 100.0 / total_sub) if total_sub > 0 else 0.0
                opts.append({
                    "id": opt.id,
                    "text": opt.text,
                    "count": c,
                    "percentage": round(pct, 2),
                })
            q_blocks.append({
                "id": q.id,
                "text": q.text,
                "required": q.required,
                "options": opts,
            })
        return {
            "id": survey.id,
            "title": survey.title,
            "description": survey.description,
            "status": survey.status,
            "creator_role": survey.creator_role,
            "total_submissions": total_sub,
            "questions": q_blocks,
        }

class SurveyAnswerReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyAnswer
        fields = ["question", "selected_option"]  # IDs تكفي للـ front

class SurveySubmissionReadSerializer(serializers.ModelSerializer):
    answers = SurveyAnswerReadSerializer(many=True, read_only=True)

    class Meta:
        model = SurveySubmission
        fields = ["id", "survey", "user", "created_at", "answers"]
        read_only_fields = fields


# =========================
# إضافات للنقاط ولوحة الشرف
# =========================

class SimpleUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'first_name', 'last_name', 'role', 'points', 'avatar', 'email']

        read_only_fields = fields


class EmployeePointLogSerializer(serializers.ModelSerializer):
    user = SimpleUserSerializer(read_only=True)
    created_by = SimpleUserSerializer(read_only=True)

    class Meta:
        model = EmployeePointLog
        fields = ['id', 'user', 'delta', 'reason', 'created_by', 'created_at']
        read_only_fields = fields


class HonorBoardEntrySerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'full_name', 'points', 'avatar']

    def get_full_name(self, obj):
        fn = (obj.first_name or '').strip()
        ln = (obj.last_name or '').strip()
        return f"{fn} {ln}".strip() or obj.username

    def get_avatar(self, obj):
        return (obj.avatar.url if getattr(obj, 'avatar', None) else None)


class HonorBoardSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    month = HonorBoardEntrySerializer(many=True)
    year  = HonorBoardEntrySerializer(many=True)
