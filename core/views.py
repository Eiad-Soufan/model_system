from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import status
from .pagination import StandardResultsSetPagination
from django.db import transaction
from django.db import models as dj_models
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from .models import CustomUser, EmployeePointLog, HonorBoardSetting
from .serializers import (
    SimpleUserSerializer,
    EmployeePointLogSerializer,
    HonorBoardSerializer,
    HonorBoardEntrySerializer,
)

from .models import Notification, UserNotification, Section, FormModel, Complaint
from .serializers import (
    SectionSerializer,
    FormModelSerializer,
    NotificationSerializer,
    UserNotificationSerializer,
    ComplaintSerializer,
    MyTokenObtainPairSerializer
)

from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import get_user_model
User = get_user_model()

class IsHR(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and getattr(request.user, 'role', '').lower() == 'hr'
        )



# 🔑 توكين JWT مخصص لإرجاع صلاحيات المستخدم
class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer


# 🔐 معلومات المستخدم الحالي
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def current_user_info(request):
    user = request.user
    return Response({
        'username': user.username,
        'is_staff': user.is_staff,
        'is_superuser': user.is_superuser,
        'id': user.id,
        'email': user.email,
        'role':  user.role
    })


# 📋 عرض المستخدمين بالأسماء لاختيار الإشعار
class UserListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        users = User.objects.all().values('id', 'username', 'email')
        return Response(list(users))


# 🌐 عرض النموذج للعامة بدون حماية
@api_view(['GET'])
def public_form_preview(request, pk):
    try:
        form = FormModel.objects.get(pk=pk)
        return FileResponse(form.file.open(), content_type='application/pdf')
    except FormModel.DoesNotExist:
        raise Http404("Form not found")
from django.http import HttpResponse, FileResponse
from django.shortcuts import get_object_or_404
from datetime import datetime
from io import BytesIO

from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

from .models import FormModel
from django.http import HttpResponse, FileResponse
import time
import threading

_LAST_NS = 0
_LAST_NS_LOCK = threading.Lock()

def _unique_time_ns() -> int:
    global _LAST_NS
    ns = time.time_ns()
    with _LAST_NS_LOCK:
        if ns <= _LAST_NS:
            ns = _LAST_NS + 1   # نضمن التزايد وعدم التكرار
        _LAST_NS = ns
    return ns


def preview_form(request, form_id):
    """
    يعرض ملف PDF مع ختم سفلي ثابت:
      Serial Number: <19-digit ns> | Date: <YYYY-mm-dd HH:MM:SS.%f>
    الرقم مبني على time.time_ns() مع ضمان تفرد داخل العملية.
    """
    form = get_object_or_404(FormModel, id=form_id)

    # 1) قراءة PDF كـ bytes
    try:
        with form.file.open('rb') as f:
            original_pdf_bytes = f.read()
    except Exception:
        return FileResponse(form.file.open('rb'), content_type='application/pdf')

    # 2) توليد رقم نانوي فريد + التاريخ المكافئ بدقة ميكروثانية للعرض
    ns = _unique_time_ns()  # 19 خانة
    human = datetime.fromtimestamp(ns / 1_000_000_000).strftime("%Y-%m-%d %H:%M:%S.%f")
    stamp_text = f"Serial Number: {ns} | Date: {human}"

    # 3) طبقة الختم
    def _make_stamp_layer(page_width, page_height, text, font_size=9):
        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=(page_width, page_height))
        c.setFont("Helvetica", font_size)
        c.setFillGray(0.35)
        margin_x = 12 * mm
        margin_y = 4 * mm   # أقرب للحافة السفلية
        c.drawRightString(page_width - margin_x, margin_y, text)
        c.save()
        buf.seek(0)
        return PdfReader(buf).pages[0]

    # 4) دمج الختم داخل كل صفحات PDF
    try:
        reader = PdfReader(BytesIO(original_pdf_bytes))
        writer = PdfWriter()

        for page in reader.pages:
            w = float(page.mediabox.width)
            h = float(page.mediabox.height)
            layer = _make_stamp_layer(w, h, stamp_text)
            page.merge_page(layer)
            writer.add_page(page)

        out = BytesIO()
        writer.write(out)
        out.seek(0)
        stamped_bytes = out.read()

        resp = HttpResponse(stamped_bytes, content_type="application/pdf")
        resp['Content-Disposition'] = f'inline; filename="form-{form_id}.pdf"'
        return resp

    except Exception:
        # Fallback آمن: رجّع الملف الأصلي كما هو
        response = FileResponse(form.file.open('rb'), content_type='application/pdf')
        response['Content-Disposition'] = 'inline; filename="form.pdf"'
        return response


# 🔔 إرسال إشعار لمستخدمين أو للجميع
class NotificationViewSet(viewsets.ModelViewSet):
    pagination_class = StandardResultsSetPagination
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'])
    def send_notification(self, request):
        print(request.data)
        title = request.data.get('title')
        message = request.data.get('message')
        importance = request.data.get('importance')
        usernames = request.data.get('usernames')  # قائمة الأسماء

        notification = Notification.objects.create(
            title=title,
            message=message,
            importance=importance
        )

        if usernames:
            users = User.objects.filter(username__in=usernames)
        else:
            users = User.objects.all()

        UserNotification.objects.bulk_create([
            UserNotification(user=user, notification=notification) for user in users
        ])

        return Response({'status': 'Notification sent successfully'}, status=status.HTTP_201_CREATED)


# 📂 عرض الأقسام (Tabs)
class SectionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Section.objects.all()
    serializer_class = SectionSerializer
    permission_classes = [IsAuthenticated]


# 🗂️ عرض النماذج داخل كل قسم
class FormModelViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = FormModel.objects.all()
    serializer_class = FormModelSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        # المدير والموارد البشرية يمكنهم الوصول لكل النماذج
        if hasattr(user, 'profile') and user.profile.role in ['manager', 'hr']:
            return FormModel.objects.all()
        allowed_sections = user.usersectionpermission_set.values_list('section_id', flat=True)
        return FormModel.objects.filter(section__id__in=allowed_sections)


# 📩 إشعارات المستخدم الفردية
class UserNotificationViewSet(viewsets.ViewSet):
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsAuthenticated]

    def list(self, request):
        user_notifications = UserNotification.objects.filter(
            user=request.user
        ).order_by('-notification__created_at')

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(user_notifications, request, view=self)
        serializer = UserNotificationSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        try:
            user_notification = UserNotification.objects.get(pk=pk, user=request.user)
            user_notification.is_read = True
            user_notification.save()
            return Response({'status': 'Marked as read'})
        except UserNotification.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

# 📝 API مخصصة للشكاوى
# ====== داخل core/views.py: استبدل كتلة ComplaintViewSet بالكامل بما يلي ======
class ComplaintViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    pagination_class = StandardResultsSetPagination

    def _paginate(self, request, queryset):
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = ComplaintSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


    # 1) إرسال شكوى من موظف
    @action(detail=False, methods=['post'])
    def submit(self, request):
        serializer = ComplaintSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # الموظف رأى شكواه لحظة الإرسال، والجهة المستقبلة تراها غير مقروءة
        complaint = serializer.save(
            sender=request.user,
            is_responded=False,
            is_seen_by_recipient=False,
            is_seen_by_employee=True
        )
        return Response(ComplaintSerializer(complaint).data, status=status.HTTP_201_CREATED)

    # 2) شكاوى الموظف الحالي
    @action(detail=False, methods=['get'])
    def my_complaints(self, request):
        qs = Complaint.objects.filter(sender=request.user).order_by('-created_at')
        return self._paginate(request, qs)

    # 3) شكاوى موجّهة للـ HR
    @action(detail=False, methods=['get'])
    def hr_complaints(self, request):
        qs = Complaint.objects.filter(recipient_type='hr').order_by('-created_at')
        return self._paginate(request, qs)

    # 4) شكاوى موجّهة للمدير
    @action(detail=False, methods=['get'])
    def manager_complaints(self, request):
        qs = Complaint.objects.filter(recipient_type='manager').order_by('-created_at')
        return self._paginate(request, qs)

    # 5) رد HR على شكوى
    @action(detail=True, methods=['post'])
    def hr_reply(self, request, pk=None):
        complaint = get_object_or_404(Complaint, pk=pk, recipient_type='hr')
        response_text = request.data.get('response')
        if not response_text:
            return Response({'error': 'Response is required'}, status=400)

        complaint.response = response_text
        complaint.is_responded = True
        complaint.responded_by = request.user
        complaint.responded_at = timezone.now()
        complaint.is_seen_by_recipient = True     # الجهة المعالجة قرأتها
        complaint.is_seen_by_employee = False     # الموظف لديه رد جديد غير مقروء
        complaint.save(update_fields=[
            'response','is_responded','responded_by','responded_at',
            'is_seen_by_recipient','is_seen_by_employee'
        ])
        return Response({'status': 'Response saved'})

    # 6) رد المدير على شكوى
    @action(detail=True, methods=['post'])
    def manager_reply(self, request, pk=None):
        complaint = get_object_or_404(Complaint, pk=pk, recipient_type='manager')
        response_text = request.data.get('response')
        if not response_text:
            return Response({'error': 'Response is required'}, status=400)

        complaint.response = response_text
        complaint.is_responded = True
        complaint.responded_by = request.user
        complaint.responded_at = timezone.now()
        complaint.is_seen_by_recipient = True
        complaint.is_seen_by_employee = False
        complaint.save(update_fields=[
            'response','is_responded','responded_by','responded_at',
            'is_seen_by_recipient','is_seen_by_employee'
        ])
        return Response({'status': 'Response saved'})

    # 7) تعليم شكوى واحدة كمقروءة حسب الدور
    @action(detail=True, methods=['post'])
    def mark_seen(self, request, pk=None):
        complaint = get_object_or_404(Complaint, pk=pk)
        user = request.user
        role = getattr(user, 'role', None)

        if user == complaint.sender:
            complaint.is_seen_by_employee = True
            fields = ['is_seen_by_employee']
        elif role in ['manager', 'hr'] and complaint.recipient_type == role:
            complaint.is_seen_by_recipient = True
            fields = ['is_seen_by_recipient']
        else:
            return Response({'error': 'Not allowed'}, status=403)

        complaint.save(update_fields=fields)
        return Response({'message': 'Marked as seen'})

    # 8) تعليم الكل كمقروء (مسار يطلبه الفرونت: /api/complaints/mark_all_seen/)
    @action(detail=False, methods=['post'])
    def mark_all_seen(self, request):
        user = request.user
        role = getattr(user, 'role', None)

        if role in ['manager', 'hr']:
            Complaint.objects.filter(
                recipient_type=role,
                is_seen_by_recipient=False
            ).update(is_seen_by_recipient=True)
        else:
            Complaint.objects.filter(
                sender=user,
                is_responded=True,
                is_seen_by_employee=False
            ).update(is_seen_by_employee=True)

        return Response({'message': 'OK'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def has_unread_complaints(request):
    """
    المدير/HR: أي شكاوى موجّهة إليهم ولم تُقرأ بعد.
    الموظف: فقط الشكاوى التي تم الرد عليها ولم يقرأها الموظف بعد.
    """
    user = request.user
    role = getattr(user, 'role', None)

    if role == 'manager':
        has_new = Complaint.objects.filter(
            recipient_type='manager',
            is_seen_by_recipient=False
        ).exists()
    elif role == 'hr':
        has_new = Complaint.objects.filter(
            recipient_type='hr',
            is_seen_by_recipient=False
        ).exists()
    else:
        has_new = Complaint.objects.filter(
            sender=user,
            is_responded=True,
            is_seen_by_employee=False
        ).exists()

    return Response({'has_new': has_new})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_complaint_as_seen(request, pk):
    """
    بديل/مرادف للـ action أعلاه إذا أردت إبقاء هذا المسار القديم يعمل أيضًا:
    /api/complaints/<pk>/mark_seen/
    """
    complaint = get_object_or_404(Complaint, pk=pk)
    user = request.user
    role = getattr(user, 'role', None)

    if user == complaint.sender:
        complaint.is_seen_by_employee = True
        fields = ['is_seen_by_employee']
    elif role in ['manager', 'hr'] and complaint.recipient_type == role:
        complaint.is_seen_by_recipient = True
        fields = ['is_seen_by_recipient']
    else:
        return Response({'error': 'Not allowed'}, status=403)

    complaint.save(update_fields=fields)
    return Response({'message': 'Marked as seen'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_all_complaints_seen(request):
    """
    مسار علوي قديم (موجود في urls.py باسم mark-all-complaints-seen/).
    أبقيناه لكنه الآن يحدّث الحقول الصحيحة.
    """
    user = request.user
    role = getattr(user, 'role', None)

    if role == 'manager':
        Complaint.objects.filter(
            recipient_type='manager',
            is_seen_by_recipient=False
        ).update(is_seen_by_recipient=True)
    elif role == 'hr':
        Complaint.objects.filter(
            recipient_type='hr',
            is_seen_by_recipient=False
        ).update(is_seen_by_recipient=True)
    else:
        Complaint.objects.filter(
            sender=user,
            is_responded=True,
            is_seen_by_employee=False
        ).update(is_seen_by_employee=True)

    return Response({'status': 'All marked as seen'})

# === [Tasks Feature] Views ===
from rest_framework import viewsets as _vs, status as _status
from rest_framework.decorators import action as _action
from rest_framework.response import Response as _Response
from django.db.models import Q as _Q

from .models import Task, TaskPhase, TaskRecipient, TaskComment
from .serializers import TaskSerializer, TaskCommentSerializer, _infer_role

class TaskViewSet(_vs.ModelViewSet):
    pagination_class = StandardResultsSetPagination
    serializer_class = TaskSerializer

    def get_queryset(self):
        user = self.request.user
        role = _infer_role(user)
        base = Task.objects.all().select_related("created_by").prefetch_related("phases", "recipients", "comments")

        if role in ("manager", "general_manager"):
            return base.filter(creator_role="management").order_by("-created_at")
        if role == "hr":
            return base.filter(_Q(creator_role="hr") | _Q(recipients__is_hr_team=True)).distinct().order_by("-created_at")
        return base.filter(recipients__user_id=user.id).distinct().order_by("-created_at")

    def perform_create(self, serializer):
        role = _infer_role(self.request.user)
        if role not in ("hr", "manager", "general_manager"):
            raise PermissionError("Not allowed")
        serializer.save()

    def perform_update(self, serializer):
        instance = self.get_object()
        role = _infer_role(self.request.user)
        if role in ("manager", "general_manager") and instance.creator_role != "management":
            raise PermissionError("Managers can edit only management tasks.")
        if role == "hr" and instance.creator_role != "hr":
            raise PermissionError("HR can edit only HR tasks.")
        serializer.save()

    @_action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        task = self.get_object()
        role = _infer_role(request.user)
        if role not in ("hr", "manager", "general_manager"):
            return _Response({"detail": "Not allowed."}, status=_status.HTTP_403_FORBIDDEN)
        task.cancel(request.user)
        return _Response({"status": task.status})

    @_action(detail=True, methods=["post"], url_path="mark-failed")
    def mark_failed(self, request, pk=None):
        task = self.get_object()
        role = _infer_role(request.user)
        if role not in ("hr", "manager", "general_manager"):
            return _Response({"detail": "Not allowed."}, status=_status.HTTP_403_FORBIDDEN)
        task.mark_failed(request.user)
        return _Response({"status": task.status})

    @_action(detail=True, methods=["post"], url_path="mark-success")
    def mark_success(self, request, pk=None):
        task = self.get_object()
        role = _infer_role(request.user)
        if role not in ("hr", "manager", "general_manager"):
            return _Response({"detail": "Not allowed."}, status=_status.HTTP_403_FORBIDDEN)
        task.mark_success(request.user)
        return _Response({"status": task.status})

    @_action(detail=True, methods=["post"], url_path="complete-next-phase")
    def complete_next_phase(self, request, pk=None):
        task = self.get_object()
        user = request.user
        role = _infer_role(user)

        can_employee = task.recipients.filter(user_id=user.id).exists()
        can_hr_team = role == "hr" and task.recipients.filter(is_hr_team=True).exists()
        if not (can_employee or can_hr_team):
            return _Response({"detail": "Not allowed."}, status=_status.HTTP_403_FORBIDDEN)
        if task.status != "open":
            return _Response({"detail": "Task is already closed."}, status=_status.HTTP_400_BAD_REQUEST)

        result = (request.data or {}).get("result")
        if result not in ("success", "failed"):
            return _Response({"detail": "Invalid result."}, status=_status.HTTP_400_BAD_REQUEST)

        next_phase = task.phases.filter(status="pending").order_by("order").first()
        if not next_phase:
            return _Response({"detail": "No pending phases."}, status=_status.HTTP_400_BAD_REQUEST)

        next_phase.complete(result)
        return _Response({"phase_id": next_phase.id, "order": next_phase.order, "status": next_phase.status})

    @_action(detail=True, methods=["get", "post"], url_path="comments")
    def comments(self, request, pk=None):
        task = self.get_object()
        if request.method.lower() == "get":
            data = TaskCommentSerializer(task.comments.order_by("created_at"), many=True).data
            return _Response(data)

        if task.status != "open":
            return _Response({"detail": "Task is closed."}, status=_status.HTTP_400_BAD_REQUEST)

        text = (request.data or {}).get("text", "").strip()
        if not text:
            return _Response({"detail": "Text is required."}, status=_status.HTTP_400_BAD_REQUEST)

        user = request.user
        role = _infer_role(user)
        can_employee = task.recipients.filter(user_id=user.id).exists()
        can_hr_team = role == "hr" and task.recipients.filter(is_hr_team=True).exists()
        can_creator = role in ("manager", "general_manager", "hr")

        if not (can_employee or can_hr_team or can_creator):
            return _Response({"detail": "Not allowed."}, status=_status.HTTP_403_FORBIDDEN)

        comment = TaskComment.objects.create(task=task, author=user, text=text)
        return _Response(TaskCommentSerializer(comment).data, status=_status.HTTP_201_CREATED)




from django.db.models import Prefetch
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    Survey, SurveyQuestion, SurveyOption,
    SurveySubmission, SurveyAnswer,
    SurveyStatus, CreatorRole,
)
from .serializers import (
    SurveySerializer,
    SurveyWriteSerializer,
    SurveySubmissionWriteSerializer,
    SurveyResultsSerializer,
)

from .serializers import SurveySubmissionReadSerializer


class IsAuthenticatedAny(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class SurveyViewSet(viewsets.ModelViewSet):
    pagination_class = StandardResultsSetPagination
    """
    إدارة/عرض الاستبيانات:
    - الموظفون: list/retrieve للاستبيانات المنشورة فقط (Published)
    - المدير/HR: list/retrieve لكل استبيانات دورهم (manager/ hr)
    - create/update/destroy: المدير/HR فقط
    - submit: إرسال إجابات الموظف
    - results: نتائج الاستبيان (manager/hr فقط وبشرط نفس الدور)
    """
    permission_classes = [IsAuthenticatedAny]
    lookup_field = "pk"

    def get_queryset(self):
        user = self.request.user
        # تحسين الأداء
        base = (
            Survey.objects.select_related("creator").prefetch_related(
                Prefetch(
                    "questions",
                    queryset=SurveyQuestion.objects.all().prefetch_related("options")
                ),
                "submissions",
            )
            .order_by("-created_at")
        )

        role = (getattr(user, "role", "") or "").lower()
        if role in (CreatorRole.MANAGER, CreatorRole.HR):
            # المدير/HR: يرى فقط استبيانات الدور الخاص به (بغض النظر عن الحالة)
            return base.filter(creator_role=role)
        # الموظف (وأي دور غير معروف): يرى فقط المنشور Published
        return base.filter(status=SurveyStatus.PUBLISHED)

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return SurveyWriteSerializer
        return SurveySerializer

    # ضمان أن الإنشاء/التعديل/الحذف للمدير أو HR فقط
    def _ensure_manager_or_hr(self):
        role = (getattr(self.request.user, "role", "") or "").lower()
        if role not in (CreatorRole.MANAGER, CreatorRole.HR):
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        return None

    def perform_create(self, serializer):
        # السماح فقط للمدير/HR بالإنشاء، وضبط creator_role تلقائيًا
        deny = self._ensure_manager_or_hr()
        if deny:  # ردّ جاهز بالمنع
            raise permissions.PermissionDenied(detail="Not allowed.")

        role = (getattr(self.request.user, "role", "") or "").lower()
        serializer.save(creator=self.request.user, creator_role=role)

    def update(self, request, *args, **kwargs):
        deny = self._ensure_manager_or_hr()
        if deny:
            return deny
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        deny = self._ensure_manager_or_hr()
        if deny:
            return deny
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        deny = self._ensure_manager_or_hr()
        if deny:
            return deny
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        """
        إرسال إجابات الموظف:
        body:
        {
          "answers": [
            {"question": <id>, "selected_option": <id>},
            ...
          ]
        }
        """
        survey = self.get_object()

        # لا يسمح بالإرسال إلا على منشور Published
        if survey.status != SurveyStatus.PUBLISHED:
            return Response({"detail": "Survey is not published."}, status=status.HTTP_400_BAD_REQUEST)

        data = {
            "survey": survey.id,
            "answers": request.data.get("answers") or [],
        }
        ser = SurveySubmissionWriteSerializer(data=data, context={"request": request})
        ser.is_valid(raise_exception=True)
        sub = ser.save()
        return Response({"id": sub.id, "created_at": sub.created_at}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def results(self, request, pk=None):
        """
        عرض نتائج الاستبيان (counts + %) للمدير/HR فقط
        - ويجب أن يطابق الدور creator_role للاستبيان.
        """
        survey = self.get_object()
        role = (getattr(request.user, "role", "") or "").lower()

        if role not in (CreatorRole.MANAGER, CreatorRole.HR):
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        if role != survey.creator_role:
            return Response({"detail": "Not allowed for this survey role."}, status=status.HTTP_403_FORBIDDEN)

        ser = SurveyResultsSerializer(survey)
        return Response(ser.data, status=status.HTTP_200_OK)


    @action(detail=True, methods=["get"])
    def my_submission(self, request, pk=None):
        """
        يرجع إرسال الموظف الحالي (إن وُجد) مع الإجابات.
        الموظف فقط. المدير/HR لا معنى لهذا الأكشن لهم.
        """
        role = (getattr(request.user, "role", "") or "").lower()
        if role in (CreatorRole.MANAGER, CreatorRole.HR):
            return Response({"exists": False}, status=status.HTTP_200_OK)

        survey = self.get_object()
        sub = SurveySubmission.objects.filter(
            survey=survey, user=request.user
        ).prefetch_related("answers").first()

        if not sub:
            return Response({"exists": False}, status=status.HTTP_200_OK)

        ser = SurveySubmissionReadSerializer(sub)
        return Response({"exists": True, "submission": ser.data}, status=status.HTTP_200_OK)


    @action(detail=True, methods=["post"])
    def change_status(self, request, pk=None):
        survey = self.get_object()
        role = (getattr(request.user, "role", "") or "").lower()
        if role not in ("manager", "hr"):
            return Response({"detail": "Not allowed"}, status=status.HTTP_403_FORBIDDEN)

        new_status = request.data.get("status")
        if new_status not in ["draft", "published", "archived"]:
            return Response({"detail": "Invalid status"}, status=status.HTTP_400_BAD_REQUEST)

        survey.status = new_status
        survey.save(update_fields=["status"])
        return Response({"status": survey.status}, status=status.HTTP_200_OK)
    

    # ============================
# إدارة النقاط ولوحة الشرف
# ============================

class EmployeeSearchView(APIView):
    permission_classes = [IsHR]
    def get(self, request):
        q = (request.query_params.get('q') or '').strip()
        qs = CustomUser.objects.all().order_by('first_name', 'last_name', 'username')
        if q:
            qs = qs.filter(
                dj_models.Q(username__icontains=q) |
                dj_models.Q(first_name__icontains=q) |
                dj_models.Q(last_name__icontains=q)
            )
        return Response(SimpleUserSerializer(qs[:200], many=True).data)


class AdjustPointsView(APIView):
    permission_classes = [IsHR]

    @transaction.atomic
    def post(self, request):
        user_id = request.data.get('user_id')
        try:
            delta = int(request.data.get('delta', 0))
        except (TypeError, ValueError):
            return Response({'detail': 'Invalid delta'}, status=status.HTTP_400_BAD_REQUEST)

        reason = (request.data.get('reason') or '').strip()
        try:
            target = CustomUser.objects.select_for_update().get(pk=user_id)
        except CustomUser.DoesNotExist:
            return Response({'detail': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        target.points = (target.points or 0) + delta
        target.save(update_fields=['points'])
        log = EmployeePointLog.objects.create(user=target, delta=delta, reason=reason, created_by=request.user)
        return Response(EmployeePointLogSerializer(log).data, status=status.HTTP_201_CREATED)


# عرض لوحة الشرف (لجميع المستخدمين)
class HonorBoardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        s = HonorBoardSetting.get_singleton()

        now = timezone.now()
        start_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_year  = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

        def winners_since(dt):
            scores = (EmployeePointLog.objects
                      .filter(created_at__gte=dt)
                      .values('user').annotate(score=dj_models.Sum('delta')))
            scores = list(scores)
            if not scores:
                return []
            max_score = max(s['score'] for s in scores)
            winners_ids = sorted([s['user'] for s in scores if s['score'] == max_score])
            return CustomUser.objects.filter(id__in=winners_ids).order_by('first_name', 'last_name', 'username')

        payload = {
            'enabled_month': bool(s.enabled_month),
            'enabled_year' : bool(s.enabled_year),
            'enabled'      : bool(s.enabled_month or s.enabled_year),  # للتوافق مع الواجهات القديمة إن احتاجت
            'month': HonorBoardEntrySerializer(winners_since(start_month), many=True).data if s.enabled_month else [],
            'year' : HonorBoardEntrySerializer(winners_since(start_year),  many=True).data if s.enabled_year  else [],
        }
        return Response(payload)


class HonorBoardToggleView(APIView):
    permission_classes = [IsHR]
    """
    يقبل:
    { "scope": "month" | "year" | "both", "enabled": true/false }
    - إن لم تُرسل scope سيتم اعتبار "both"
    - يعيد الحالة كاملة (enabled_month, enabled_year, enabled)
    """
    def patch(self, request):
        scope = (request.data.get('scope') or 'both').lower()
        enabled = bool(request.data.get('enabled', True))
        s = HonorBoardSetting.get_singleton()
        if scope == 'month':
            s.enabled_month = enabled
        elif scope == 'year':
            s.enabled_year = enabled
        else:  # both
            s.enabled_month = enabled
            s.enabled_year  = enabled
        s.save(update_fields=['enabled_month', 'enabled_year'])
        return Response({
            'enabled_month': s.enabled_month,
            'enabled_year' : s.enabled_year,
            'enabled'      : s.enabled_month or s.enabled_year,
        })
    post = patch


# رفع صورة البروفايل
class AvatarUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        f = request.FILES.get('avatar')
        if not f:
            return Response({'detail': 'No file provided'}, status=400)
        u = request.user
        u.avatar = f
        u.save(update_fields=['avatar'])
        return Response({'avatar': u.avatar.url})
    
from rest_framework.generics import RetrieveAPIView
from .serializers import SimpleUserSerializer    

class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        u = request.user
        # نرجّع الحقول التي تحتاجها الواجهة بالضبط
        payload = {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "first_name": u.first_name or "",
            "last_name": u.last_name or "",
            "role": getattr(u, "role", "employee"),
            "points": getattr(u, "points", 0),
            "avatar": (u.avatar.url if getattr(u, "avatar", None) else None),
        }
        return Response(payload)